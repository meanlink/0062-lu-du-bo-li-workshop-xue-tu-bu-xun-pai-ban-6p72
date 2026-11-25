"""HTTP 端到端测试：停课关闭接口的鉴权、响应结构与并发口径。

DATABASE_URL=postgresql://app@127.0.0.1:17956/business_test \
python3 -m tests.test_api
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATABASE_URL", "postgresql://app@127.0.0.1:17956/business_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")

import psycopg
from fastapi.testclient import TestClient

import core
import app as app_module

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
app_module.CACHE = FakeCache()

T0 = datetime(2026, 11, 24, 14, 0, tzinfo=timezone(timedelta(hours=8)))
PASS, FAIL = [], []

def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(f"{'✓' if condition else '✗'} {name}" + (f" — {detail}" if detail and not condition else ""))

def reset_db():
    with psycopg.connect(os.environ["DATABASE_URL"]) as cx:
        cx.execute((BACKEND / "schema.sql").read_text())
        core.initialize(cx, (BACKEND / "schema.sql").read_text())
        cx.execute("""
            TRUNCATE coaching_makeup, coaching_assignments, apprentice_profiles,
                     skill_observations, coaching_slots, apprentices, app_users
                     RESTART IDENTITY CASCADE""")
        core.seed_users(cx)
        cx.commit()

def seed_scenario(cx):
    for code, name in (("A-04", "徐晨"), ("A-09", "苏渝")):
        cx.execute(
            "INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on) VALUES (%s,%s,'11 月','乔育',true,'2026-11-06')",
            (code, name))
        cx.execute(
            "INSERT INTO skill_observations(code,apprentice,noted_on,setup,handoff,teardown,source) VALUES (%s,%s,'2026-11-20',7,8,7,'r.csv')",
            (f"O-{code}", code))
        cx.execute(
            "INSERT INTO apprentice_profiles(apprentice,discipline,n_distinct,margin,drivers,observation) VALUES (%s,'handoff',3,2.5,'{}'::jsonb,%s)",
            (code, f"O-{code}"))
    cx.execute("INSERT INTO coaching_slots(code,discipline,starts_at,capacity,instructor) VALUES ('C-14','handoff',%s,2,'乔育')", (T0,))
    cx.execute("INSERT INTO coaching_slots(code,discipline,starts_at,capacity,instructor) VALUES ('C-18','handoff',%s,1,'乔育')", (T0 + timedelta(days=1),))
    cx.execute("INSERT INTO coaching_slots(code,discipline,starts_at,capacity,instructor) VALUES ('C-16','bench',%s,2,'施北')", (T0 + timedelta(days=1),))

def token(client, role):
    resp = client.post("/api/auth/login", json={"email": f"{role}@demo.local", "password": "Demo2026!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]

def auth(role):
    return {"Authorization": f"Bearer {token(client, role)}"}

client = TestClient(app_module.app)

def main():
    reset_db()
    with core.db() as cx:
        seed_scenario(cx)

    # 未登录 → 401
    check("未登录关闭班次被拒", client.post("/api/clinics/C-14/close", json={}).status_code == 401)
    # 查阅员 → 403
    check("查阅员无权关闭班次", client.post("/api/clinics/C-14/close", json={}, headers=auth("viewer")).status_code == 403)

    reviewer = auth("reviewer")
    # 复核员签核两人进 C-14
    for code in ("A-04", "A-09"):
        r = client.post("/api/clinics/assign", json={"apprentice": code, "slot": "C-14"}, headers=reviewer)
        check(f"签核 {code}", r.status_code == 200, r.text)

    # 排班查询包含待补字段
    data = client.get("/api/clinics", headers=reviewer).json()
    check("排班查询返回 makeup 字段", "makeup" in data and data["makeup"] == [])
    check("排班查询返回班次关闭标记", all("closed" in s for s in data["slots"]))

    # 关闭 C-14：C-18 容量 1，只迁得走一人，另一人待补
    r = client.post("/api/clinics/C-14/close", json={"reason": "导师临时调岗"}, headers=reviewer)
    check("停课关闭 200", r.status_code == 200, r.text)
    body = r.json()
    check("返回迁移 1 人", len(body["moved"]) == 1, str(body["moved"]))
    check("返回待补 1 人", len(body["waiting"]) == 1, str(body["waiting"]))
    check("迁移目标为同方向最近后续 C-18", body["moved"][0]["slot"] == "C-18")
    with core.db() as cx:
        reason = cx.execute("SELECT closed_reason FROM coaching_slots WHERE code='C-14'").fetchone()["closed_reason"]
    check("停课原因已落库", reason == "导师临时调岗", reason)

    # 重复关闭：幂等
    r2 = client.post("/api/clinics/C-14/close", json={}, headers=reviewer)
    check("重复停课 200 且标记 repeated", r2.status_code == 200 and r2.json()["repeated"] is True)
    check("重复停课不新增迁移", r2.json()["moved"] == body["moved"])

    # 关闭班次拒绝新签核
    r = client.post("/api/clinics/assign", json={"apprentice": "A-04", "slot": "C-14"}, headers=reviewer)
    check("关闭班次拒绝新签核 409", r.status_code == 409, r.text)

    # 页面查询：受影响学徒去向与原签核依据齐全
    data = client.get("/api/clinics", headers=reviewer).json()
    moved_row = next(a for a in data["assignments"] if a["apprentice"] == body["moved"][0]["apprentice"])
    check("迁席记录带原班次依据", moved_row["origin_slot"] == "C-14" and moved_row["origin_signed_by"])
    check("待补队列带原签核依据",
          len(data["makeup"]) == 1 and data["makeup"][0]["origin_slot"] == "C-14"
          and data["makeup"][0]["origin_signed_by"] and data["makeup"][0]["discipline"] == "handoff")
    closed_slot = next(s for s in data["slots"] if s["code"] == "C-14")
    check("班次状态为已关闭", closed_slot["closed"] is True)

    # 撤席触发待补补位：先占满 C-18，再撤出
    with core.db() as cx:
        cx.execute("INSERT INTO apprentices(code,name,cohort,mentor,eligible,joined_on) VALUES ('A-21','罗盏','11 月','施北',true,'2026-11-06')")
        cx.execute("INSERT INTO skill_observations(code,apprentice,noted_on,setup,handoff,teardown,source) VALUES ('O-A-21','A-21','2026-11-20',7,8,7,'r.csv')")
        cx.execute("INSERT INTO apprentice_profiles(apprentice,discipline,n_distinct,margin,drivers,observation) VALUES ('A-21','handoff',3,2.5,'{}'::jsonb,'O-A-21')")
        cx.commit()
    # C-18 已被迁席者占满（容量 1）；直接撤该迁席者 → 待补者补位
    occupant = body["moved"][0]["apprentice"]
    r = client.post(f"/api/clinics/{occupant}/release", json={}, headers=reviewer)
    check("撤席接口 200", r.status_code == 200, r.text)
    filled = r.json()["makeup_filled"]
    check("撤席后自动补待补学徒", len(filled) == 1 and filled[0]["apprentice"] == body["waiting"][0]["apprentice"], str(filled))
    data = client.get("/api/clinics", headers=reviewer).json()
    check("补位后待补队列清空", data["makeup"] == [])

    # 不存在的班次 → 404
    check("关闭不存在班次 404", client.post("/api/clinics/NOPE/close", json={}, headers=reviewer).status_code == 404)

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项:", FAIL)
        sys.exit(1)

if __name__ == "__main__":
    main()
