"""集成测试：停课关闭班次、迁移、待补与撤席补位。

运行：
  DATABASE_URL=postgresql://app@127.0.0.1:17956/business_test \
  REDIS_URL=redis://localhost:6379/0 JWT_SECRET=test-secret \
  python3 -m tests.test_closures
"""
import os
import sys
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATABASE_URL", "postgresql://app@127.0.0.1:17956/business_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")

import psycopg
from psycopg.rows import dict_row

import core
from clinic_assignments import Assignment, close_slot, release, sign

# ---- 用内存假 Redis 顶替，测试环境不依赖 redis-server ----
class FakePipeline:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def incr(self, *_): return self
    def expire(self, *a, **k): return self
    def execute(self): return (1, True)

class FakeCache:
    def ping(self): return True
    def pipeline(self): return FakePipeline()

core.CACHE = FakeCache()

T0 = datetime(2026, 11, 24, 14, 0, tzinfo=timezone(timedelta(hours=8)))
PASS, FAIL = [], []

def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(f"{'✓' if condition else '✗'} {name}" + (f" — {detail}" if detail and not condition else ""))

def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)

def reset(cx):
    cx.execute("""
        TRUNCATE coaching_makeup, coaching_assignments, apprentice_profiles,
                 skill_observations, coaching_slots, apprentices RESTART IDENTITY CASCADE""")

def seed_base(cx):
    """4 名在训学徒，均为 handoff 方向、余量充足；5 个 handoff 班次。"""
    apprentices = [("A-04", "徐晨"), ("A-09", "苏渝"), ("A-15", "马井"), ("A-21", "罗盏")]
    for code, name in apprentices:
        cx.execute(
            "INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on) VALUES (%s,%s,'11 月','乔育',true,'2026-11-06')",
            (code, name))
        cx.execute(
            "INSERT INTO skill_observations(code,apprentice,noted_on,setup,handoff,teardown,source) VALUES (%s,%s,'2026-11-20',7,8,7,'轮训记录.csv')",
            (f"O-{code}", code))
        cx.execute(
            """INSERT INTO apprentice_profiles(apprentice,discipline,n_distinct,margin,drivers,observation)
               VALUES (%s,'handoff',3,2.5,'{}'::jsonb,%s)""",
            (code, f"O-{code}"))
    slots = [
        ("C-14", T0, 3),
        ("C-18", T0 + timedelta(hours=25, minutes=30), 2),
        ("C-20", T0 + timedelta(days=2), 1),
        ("C-21", T0 + timedelta(days=3), 2),
        ("C-22", T0 + timedelta(days=4), 10),
    ]
    for code, starts, cap in slots:
        cx.execute(
            "INSERT INTO coaching_slots(code,discipline,starts_at,capacity,instructor) VALUES (%s,'handoff',%s,%s,'乔育')",
            (code, starts, cap))

def sign_three(cx):
    for code in ("A-04", "A-09", "A-15"):
        sign(cx, Assignment(apprentice=code, slot="C-14"), "reviewer@demo.local")
    # 明确原签核先后
    cx.execute("UPDATE coaching_assignments SET assigned_at=%s WHERE apprentice='A-04'", (T0 - timedelta(hours=3),))
    cx.execute("UPDATE coaching_assignments SET assigned_at=%s WHERE apprentice='A-09'", (T0 - timedelta(hours=2),))
    cx.execute("UPDATE coaching_assignments SET assigned_at=%s WHERE apprentice='A-15'", (T0 - timedelta(hours=1),))

def slot_of(cx, apprentice):
    row = cx.execute("SELECT slot FROM coaching_assignments WHERE apprentice=%s", (apprentice,)).fetchone()
    return row["slot"] if row else None

# ---- 场景 1：按原签核先后迁往同方向最近后续余席，其他班次的人不动 ----
def test_migration_order():
    with connect() as cx:
        reset(cx); seed_base(cx); sign_three(cx)
        # 其他班次已签的人照旧
        sign(cx, Assignment(apprentice="A-21", slot="C-22"), "reviewer@demo.local")
        result = close_slot(cx, "C-14", "reviewer@demo.local")
        check("场景1 迁移人数=3", len(result["moved"]) == 3, str(result["moved"]))
        check("场景1 A-04→C-18（最近）", slot_of(cx, "A-04") == "C-18")
        check("场景1 A-09→C-18（同班第二席）", slot_of(cx, "A-09") == "C-18")
        check("场景1 C-18 满 2 席后 A-15→C-20", slot_of(cx, "A-15") == "C-20")
        check("场景1 迁移顺序按原签核先后",
              [m["apprentice"] for m in result["moved"]] == ["A-04", "A-09", "A-15"])
        check("场景1 其他班次已签者照旧（A-21 仍在 C-22）", slot_of(cx, "A-21") == "C-22")
        row = cx.execute("SELECT * FROM coaching_assignments WHERE apprentice='A-04'").fetchone()
        check("场景1 迁移后保留原签核依据",
              row["origin_slot"] == "C-14" and row["origin_signed_by"] == "reviewer@demo.local"
              and row["origin_assigned_at"] == T0 - timedelta(hours=3))
        check("场景1 无待补记录", cx.execute("SELECT count(*) n FROM coaching_makeup").fetchone()["n"] == 0)
        check("场景1 各班次均未超售", all(
            r["occupied"] <= r["capacity"] for r in cx.execute(
                "SELECT capacity, count(a.apprentice) occupied FROM coaching_slots s LEFT JOIN coaching_assignments a ON a.slot=s.code GROUP BY s.code,s.capacity"
            ).fetchall()))

# ---- 场景 2：无后续余席 → 待补，保留原签核依据 ----
def test_makeup_queue():
    with connect() as cx:
        reset(cx); seed_base(cx); sign_three(cx)
        cx.execute("UPDATE coaching_slots SET capacity=1 WHERE code IN ('C-18','C-20','C-21')")
        # C-18/C-20/C-21 各占 1 席，全部满员；C-22 不同方向不可用——这里全部是 handoff，
        # 故把 C-22 关闭，保证没有任何后续余席
        cx.execute("UPDATE coaching_slots SET closed=true WHERE code='C-22'")
        for code, occ in (("C-18", "A-21"),):
            sign(cx, Assignment(apprentice=occ, slot=code), "reviewer@demo.local")
        # C-20、C-21 也占满：借用 A-21 只能占一个，改为直接插两条历史占席
        cx.execute("""INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on)
                      VALUES ('A-31','占席甲','11 月','施北',true,'2026-11-06'),
                             ('A-32','占席乙','11 月','施北',true,'2026-11-06')""")
        for code, occ in (("C-20", "A-31"), ("C-21", "A-32")):
            cx.execute(
                "INSERT INTO coaching_assignments(apprentice,slot,recommended,signed_by) VALUES (%s,%s,'handoff','r@x')",
                (occ, code))
        result = close_slot(cx, "C-14", "reviewer@demo.local")
        check("场景2 无人可迁", result["moved"] == [])
        check("场景2 3 人全部待补", len(result["waiting"]) == 3, str(result["waiting"]))
        order = [r["apprentice"] for r in cx.execute(
            "SELECT apprentice FROM coaching_makeup ORDER BY origin_assigned_at,apprentice").fetchall()]
        check("场景2 待补顺序沿用原签核先后", order == ["A-04", "A-09", "A-15"], str(order))
        m = cx.execute("SELECT * FROM coaching_makeup WHERE apprentice='A-04'").fetchone()
        check("场景2 待补保留原签核依据",
              m["origin_slot"] == "C-14" and m["origin_signed_by"] == "reviewer@demo.local"
              and m["discipline"] == "handoff")
        # 待补者不能再走新签核（C-23 是开放但已满的同方向班次也应被前置拦截）
        cx.execute("INSERT INTO coaching_slots(code,discipline,starts_at,capacity,instructor) VALUES ('C-23','handoff',%s,3,'施北')",
                   (T0 + timedelta(days=5),))
        try:
            sign(cx, Assignment(apprentice="A-04", slot="C-23"), "reviewer@demo.local")
            check("场景2 待补者新签核被拒", False)
        except Exception as exc:
            check("场景2 待补者新签核被拒", getattr(exc, "status_code", None) == 409, str(exc))

# ---- 场景 3：撤席先补待补（按原签核顺序），补位优先于新签核 ----
def test_release_fills_makeup():
    with connect() as cx:
        reset(cx); seed_base(cx); sign_three(cx)
        # 让所有后续 handoff 班次满员，停课后三人全部进入待补
        cx.execute("UPDATE coaching_slots SET capacity=1 WHERE code IN ('C-18','C-20','C-21')")
        cx.execute("UPDATE coaching_slots SET closed=true WHERE code='C-22'")
        cx.execute("""INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on)
                      VALUES ('A-31','占席甲','11 月','施北',true,'2026-11-06'),
                             ('A-32','占席乙','11 月','施北',true,'2026-11-06')""")
        cx.execute("INSERT INTO coaching_assignments(apprentice,slot,recommended,signed_by) VALUES ('A-31','C-18','handoff','r@x')")
        cx.execute("INSERT INTO coaching_assignments(apprentice,slot,recommended,signed_by) VALUES ('A-32','C-20','handoff','r@x')")
        # C-21 容量 1 但空着也会被迁移占用：先占上它
        cx.execute("""INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on)
                      VALUES ('A-33','占席丙','11 月','施北',true,'2026-11-06')""")
        cx.execute("INSERT INTO coaching_assignments(apprentice,slot,recommended,signed_by) VALUES ('A-33','C-21','handoff','r@x')")
        close_slot(cx, "C-14", "reviewer@demo.local")
        check("场景3 待补 3 人", cx.execute("SELECT count(*) n FROM coaching_makeup").fetchone()["n"] == 3)
        # 撤出 C-18 的占席 → 待补第一人 A-04 立即补进 C-18
        out = release(cx, "A-31")
        check("场景3 撤席返回补位结果", out["makeup_filled"][0]["apprentice"] == "A-04", str(out))
        check("场景3 A-04 补进被撤的 C-18", slot_of(cx, "A-04") == "C-18")
        check("场景3 补位后移出待补队列",
              cx.execute("SELECT count(*) n FROM coaching_makeup WHERE apprentice='A-04'").fetchone()["n"] == 0)
        row = cx.execute("SELECT * FROM coaching_assignments WHERE apprentice='A-04'").fetchone()
        check("场景3 补位仍带原签核依据", row["origin_slot"] == "C-14"
              and row["origin_signed_by"] == "reviewer@demo.local")
        remaining = [r["apprentice"] for r in cx.execute(
            "SELECT apprentice FROM coaching_makeup ORDER BY origin_assigned_at,apprentice").fetchall()]
        check("场景3 剩余待补顺序 A-09,A-15", remaining == ["A-09", "A-15"], str(remaining))
        # 再撤 C-20 的占席 → A-09 按序补上，A-15 继续等待
        release(cx, "A-32")
        check("场景3 第二次撤席补 A-09", slot_of(cx, "A-09") == "C-20")
        check("场景3 仅剩 A-15 待补",
              [r["apprentice"] for r in cx.execute("SELECT apprentice FROM coaching_makeup").fetchall()] == ["A-15"])
        # 此时新签核 A-15 之外的学徒进 C-20 会被满员拒绝；待补优先于新签核的口径已由补位顺序验证
        try:
            sign(cx, Assignment(apprentice="A-21", slot="C-20"), "reviewer@demo.local")
            check("场景3 满员班次拒绝新签核", False)
        except Exception as exc:
            check("场景3 满员班次拒绝新签核", getattr(exc, "status_code", None) == 409)
        # 撤掉最后一个占席：剩余的待补者 A-15 立即补进 C-21
        out = release(cx, "A-33")
        check("场景3 撤席自动补位最后一名待补者",
              [f["apprentice"] for f in out["makeup_filled"]] == ["A-15"], str(out))
        check("场景3 A-15 自动补进空出的 C-21", slot_of(cx, "A-15") == "C-21")
        check("场景3 待补队列清空",
              cx.execute("SELECT count(*) n FROM coaching_makeup").fetchone()["n"] == 0)

# ---- 场景 4：重复停课不重复迁席 ----
def test_repeated_close_idempotent():
    with connect() as cx:
        reset(cx); seed_base(cx); sign_three(cx)
        first = close_slot(cx, "C-14", "reviewer@demo.local")
        second = close_slot(cx, "C-14", "reviewer@demo.local")
        check("场景4 第二次停课标记 repeated", second["repeated"] is True)
        check("场景4 重复停课不重复迁席", second["moved"] == first["moved"])
        total = cx.execute("SELECT count(*) n FROM coaching_assignments").fetchone()["n"]
        check("场景4 签核记录不重复（仍为 3 条）", total == 3, f"n={total}")
        check("场景4 班次保持关闭",
              cx.execute("SELECT closed FROM coaching_slots WHERE code='C-14'").fetchone()["closed"] is True)
        # 已关闭班次不能再签核
        try:
            sign(cx, Assignment(apprentice="A-21", slot="C-14"), "reviewer@demo.local")
            check("场景4 关闭班次拒绝新签核", False)
        except Exception as exc:
            check("场景4 关闭班次拒绝新签核", getattr(exc, "status_code", None) == 409)

# ---- 场景 5：停课与签核并发不超售 ----
def test_concurrent_no_oversell():
    with connect() as cx:
        reset(cx); seed_base(cx)
        # C-14 容量 1，A-04 已占；并发：停课 C-14 与 A-09 新签 C-18（容量 1）
        sign(cx, Assignment(apprentice="A-04", slot="C-14"), "reviewer@demo.local")
        cx.execute("UPDATE coaching_slots SET capacity=1 WHERE code='C-18'")
    barrier = threading.Barrier(2)
    errors = []
    def close_worker():
        try:
            with connect() as c:
                barrier.wait()
                close_slot(c, "C-14", "reviewer@demo.local")
        except Exception:
            errors.append("close:" + traceback.format_exc())
    def sign_worker():
        try:
            with connect() as c:
                barrier.wait()
                sign(c, Assignment(apprentice="A-09", slot="C-18"), "reviewer@demo.local")
        except Exception as exc:
            errors.append("sign:" + str(exc))
    threads = [threading.Thread(target=close_worker), threading.Thread(target=sign_worker)]
    for t in threads: t.start()
    for t in threads: t.join()
    with connect() as cx:
        counts = {r["slot"]: r["n"] for r in cx.execute(
            "SELECT slot,count(*) n FROM coaching_assignments GROUP BY slot").fetchall()}
        caps = {r["code"]: r["capacity"] for r in cx.execute("SELECT code,capacity FROM coaching_slots").fetchall()}
        check("场景5 并发后所有班次不超售",
              all(n <= caps[s] for s, n in counts.items()), str(counts))
        check("场景5 并发线程无意外错误", not errors, errors[:1])
        occupants = {r["apprentice"]: r["slot"] for r in cx.execute(
            "SELECT apprentice,slot FROM coaching_assignments").fetchall()}
        check("场景5 两人各有一席且不重叠",
              len(occupants) == 2 and len(set(occupants.values())) == 2, str(occupants))
        check("场景5 停课后 A-04 有明确去向（迁席或待补）",
              occupants.get("A-04") is not None or cx.execute(
                  "SELECT 1 FROM coaching_makeup WHERE apprentice='A-04'").fetchone() is not None)

# ---- 场景 6：超售压测——多个签核与停课同时抢同一个 1 席班次 ----
def test_stress_oversell():
    with connect() as cx:
        reset(cx); seed_base(cx)
        cx.execute("UPDATE coaching_slots SET capacity=1 WHERE code='C-18'")
        # C-14 三人，停课会争抢 C-18 的唯一余席；同时两个新签核也抢 C-18
        sign_three(cx)
    start = threading.Barrier(4)
    errors = []
    def run(fn):
        try:
            start.wait()
            with connect() as c:
                fn(c)
        except Exception as exc:
            errors.append(str(exc))
    jobs = [
        lambda c: close_slot(c, "C-14", "reviewer@demo.local"),
        lambda c: sign(c, Assignment(apprentice="A-21", slot="C-18"), "r@x"),
    ]
    # 再加两个并发停课重试（幂等性 + 锁竞争）
    jobs += [lambda c: close_slot(c, "C-14", "reviewer@demo.local")] * 2
    threads = [threading.Thread(target=run, args=(fn,)) for fn in jobs]
    for t in threads: t.start()
    for t in threads: t.join()
    with connect() as cx:
        c18 = cx.execute("SELECT count(*) n FROM coaching_assignments WHERE slot='C-18'").fetchone()["n"]
        check("场景6 C-18 绝不为 2+ 人", c18 <= 1, f"occupied={c18}")
        check("场景6 全部学徒去向确定（3 人在签核表或待补表，不重不漏）",
              cx.execute("""SELECT count(*) n FROM (
                  SELECT apprentice FROM coaching_assignments WHERE apprentice IN ('A-04','A-09','A-15')
                  UNION SELECT apprentice FROM coaching_makeup WHERE apprentice IN ('A-04','A-09','A-15')
              ) q""").fetchone()["n"] == 3)
        check("场景6 仅有预期的 409 冲突错误，无数据库错误",
              all("409" in e for e in errors), errors[:2])

# ---- 场景 7：链式停课——再次关闭迁入班次，原签核依据不被覆盖，顺序仍按原签核 ----
def test_chained_closure_keeps_origin():
    with connect() as cx:
        reset(cx); seed_base(cx); sign_three(cx)
        first = close_slot(cx, "C-14", "reviewer@demo.local")
        # A-04、A-09 在 C-18，A-15 在 C-20
        check("场景7 首次迁移落位", slot_of(cx, "A-04") == "C-18" and slot_of(cx, "A-15") == "C-20")
        # 把后续班次全部关闭/占满，只留 C-21 有余席；再停 C-18
        cx.execute("UPDATE coaching_slots SET closed=true WHERE code='C-22'")
        cx.execute("UPDATE coaching_slots SET capacity=1 WHERE code='C-21'")
        second = close_slot(cx, "C-18", "reviewer@demo.local")
        check("场景7 二次停课产生迁移", {m["apprentice"] for m in second["moved"]} == {"A-04", "A-09"}
              or len(second["moved"]) + len(second["waiting"]) == 2, str(second))
        row = cx.execute("SELECT * FROM coaching_assignments WHERE apprentice='A-04'").fetchone()
        check("场景7 原签核班次仍是 C-14（不被 C-18 覆盖）", row and row["origin_slot"] == "C-14",
              str(row))
        if row:
            check("场景7 原签核人/时间保留",
                  row["origin_signed_by"] == "reviewer@demo.local"
                  and row["origin_assigned_at"] == T0 - timedelta(hours=3))
        # 若 A-09 落入待补，待补依据同样指向 C-14
        m = cx.execute("SELECT * FROM coaching_makeup WHERE apprentice='A-09'").fetchone()
        if m:
            check("场景7 待补依据沿用最早原签核", m["origin_slot"] == "C-14"
                  and m["origin_assigned_at"] == T0 - timedelta(hours=2))
        else:
            check("场景7 A-09 已再次迁席且依据保留",
                  cx.execute("SELECT origin_slot FROM coaching_assignments WHERE apprentice='A-09'")
                  .fetchone()["origin_slot"] == "C-14")
        check("场景7 全程不超售", all(
            r["occupied"] <= r["capacity"] for r in cx.execute(
                "SELECT capacity, count(a.apprentice) occupied FROM coaching_slots s LEFT JOIN coaching_assignments a ON a.slot=s.code GROUP BY s.code,s.capacity"
            ).fetchall()))

# ---- 场景 8：同方向有待补学徒时，任何新签核都被拒，余席只留给补位 ----
def test_no_new_sign_while_makeup_waiting():
    with connect() as cx:
        reset(cx); seed_base(cx); sign_three(cx)
        # 额外准备一个后续 handoff 班次，稍后重开验证新签核恢复
        cx.execute("INSERT INTO coaching_slots(code,discipline,starts_at,capacity,instructor) VALUES ('C-23','handoff',%s,3,'施北')",
                   (T0 + timedelta(days=5),))
        # 占满 C-18、C-20、C-21，关闭 C-22、C-23，保证停课时无人可迁
        cx.execute("UPDATE coaching_slots SET capacity=1 WHERE code IN ('C-18','C-20','C-21')")
        cx.execute("UPDATE coaching_slots SET closed=true WHERE code IN ('C-22','C-23')")
        cx.execute("""INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on)
                      VALUES ('A-31','占席甲','11 月','施北',true,'2026-11-06'),
                             ('A-32','占席乙','11 月','施北',true,'2026-11-06'),
                             ('A-33','占席丙','11 月','施北',true,'2026-11-06')""")
        for occ, code in (("A-31", "C-18"), ("A-32", "C-20"), ("A-33", "C-21")):
            cx.execute("INSERT INTO coaching_assignments(apprentice,slot,recommended,signed_by) VALUES (%s,%s,'handoff','r@x')", (occ, code))
        close_slot(cx, "C-14", "reviewer@demo.local")
        check("场景8 待补队列有 3 人", cx.execute("SELECT count(*) n FROM coaching_makeup").fetchone()["n"] == 3)
        # 重开一个 handoff 余席班次，新签核仍须让位给待补
        cx.execute("UPDATE coaching_slots SET closed=false, capacity=3 WHERE code='C-23'")
        try:
            sign(cx, Assignment(apprentice="A-21", slot="C-23"), "reviewer@demo.local")
            check("场景8 有待补时同方向新签核被拒", False)
        except Exception as exc:
            check("场景8 有待补时同方向新签核被拒", getattr(exc, "status_code", None) == 409, str(exc))
        # 不同方向的新签核不受影响（自建 bench 班次，需要 bench profile）
        cx.execute("INSERT INTO coaching_slots(code,discipline,starts_at,capacity,instructor) VALUES ('C-90','bench',%s,2,'施北')",
                   (T0 + timedelta(days=6),))
        cx.execute("UPDATE apprentice_profiles SET discipline='bench' WHERE apprentice='A-21'")
        sign(cx, Assignment(apprentice="A-21", slot="C-90"), "reviewer@demo.local")
        check("场景8 不同方向班次仍可新签核", slot_of(cx, "A-21") == "C-90")
        # 撤三个占席触发补位，验证队列清空后同方向新签核恢复
        release(cx, "A-31")
        release(cx, "A-32")
        release(cx, "A-33")
        check("场景8 三次撤席补完全部待补",
              cx.execute("SELECT count(*) n FROM coaching_makeup").fetchone()["n"] == 0)
        cx.execute("""INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on)
                      VALUES ('A-40','闻笙','11 月','施北',true,'2026-11-06')""")
        cx.execute("INSERT INTO skill_observations(code,apprentice,noted_on,setup,handoff,teardown,source) VALUES ('O-A-40','A-40','2026-11-22',7,8,7,'r.csv')")
        cx.execute("INSERT INTO apprentice_profiles(apprentice,discipline,n_distinct,margin,drivers,observation) VALUES ('A-40','handoff',3,2.5,'{}'::jsonb,'O-A-40')")
        sign(cx, Assignment(apprentice="A-40", slot="C-23"), "reviewer@demo.local")
        check("场景8 待补清空后同方向新签核恢复", slot_of(cx, "A-40") == "C-23")

def main():
    for fn in (test_migration_order, test_makeup_queue, test_release_fills_makeup,
               test_repeated_close_idempotent, test_concurrent_no_oversell, test_stress_oversell,
               test_chained_closure_keeps_origin, test_no_new_sign_while_makeup_waiting):
        print(f"\n=== {fn.__name__} ===")
        fn()
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项:", FAIL)
        sys.exit(1)

if __name__ == "__main__":
    main()
