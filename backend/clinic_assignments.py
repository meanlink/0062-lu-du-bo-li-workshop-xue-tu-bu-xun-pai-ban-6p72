from fastapi import HTTPException
from pydantic import BaseModel

class Assignment(BaseModel):
    apprentice: str
    slot: str

def _fill_makeup(cx, slot):
    """班次撤席后，先按原签核顺序补同方向的待补学徒，返回补位记录。"""
    row = cx.execute("SELECT * FROM coaching_slots WHERE code=%s FOR UPDATE", (slot,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这个辅导班次")
    made = []
    while True:
        occupied = cx.execute(
            "SELECT count(*) AS n FROM coaching_assignments WHERE slot=%s", (slot,)
        ).fetchone()["n"]
        if occupied >= row["capacity"]:
            break
        waiting = cx.execute(
            """SELECT m.*, a.eligible FROM coaching_makeup m
               JOIN apprentices a ON a.code=m.apprentice
               WHERE m.discipline=%s AND a.eligible
               ORDER BY m.origin_assigned_at, m.apprentice FOR UPDATE OF m SKIP LOCKED LIMIT 1""",
            (row["discipline"],),
        ).fetchone()
        if not waiting:
            break
        cx.execute("DELETE FROM coaching_makeup WHERE apprentice=%s", (waiting["apprentice"],))
        cx.execute(
            """INSERT INTO coaching_assignments
               (apprentice,slot,recommended,signed_by,assigned_at,origin_slot,origin_signed_by,origin_assigned_at)
               VALUES (%s,%s,%s,%s,now(),%s,%s,%s)""",
            (waiting["apprentice"], slot, waiting["discipline"], "system:makeup",
             waiting["origin_slot"], waiting["origin_signed_by"], waiting["origin_assigned_at"]),
        )
        made.append({"apprentice": waiting["apprentice"], "slot": slot,
                     "origin_slot": waiting["origin_slot"]})
    return made

def sign(cx,item,signer):
    student=cx.execute("SELECT eligible FROM apprentices WHERE code=%s FOR UPDATE",(item.apprentice,)).fetchone()
    choice=cx.execute("SELECT * FROM coaching_slots WHERE code=%s FOR UPDATE",(item.slot,)).fetchone()
    profile=cx.execute("SELECT * FROM apprentice_profiles WHERE apprentice=%s",(item.apprentice,)).fetchone()
    if not student or not student["eligible"] or not choice or not profile:
        raise HTTPException(409,"需确认轮训资格并先计算补训方向")
    if choice["closed"]:
        raise HTTPException(409,"该班次已停课关闭，不能再签核")
    if cx.execute("SELECT 1 FROM coaching_makeup WHERE apprentice=%s",(item.apprentice,)).fetchone():
        raise HTTPException(409,"该学徒持有停课待补签核，撤席时会按原签核顺序优先补位")
    # 同方向仍有待补学徒时，余席须先按原签核顺序补待补，不接新签核
    if cx.execute("SELECT 1 FROM coaching_makeup WHERE discipline=%s LIMIT 1",(choice["discipline"],)).fetchone():
        raise HTTPException(409,"该方向仍有停课待补学徒，须先在撤席余席中按原签核顺序补位，暂不接新签核")
    latest=cx.execute("SELECT code FROM skill_observations WHERE apprentice=%s ORDER BY noted_on DESC,code DESC LIMIT 1",(item.apprentice,)).fetchone()
    if profile["observation"] != latest["code"]:
        raise HTTPException(409,"出现新课堂观察，请重新计算方向")
    if (profile["discipline"] != choice["discipline"]) or profile["margin"] < 1:
        raise HTTPException(409,"班次方向与证据不符，或判别余量不足")
    if cx.execute("SELECT count(*) AS n FROM coaching_assignments WHERE slot=%s",(item.slot,)).fetchone()["n"] >= choice["capacity"]:
        raise HTTPException(409,"辅导席已满")
    cx.execute("INSERT INTO coaching_assignments(apprentice,slot,recommended,signed_by) VALUES (%s,%s,%s,%s)",
         (item.apprentice,item.slot,profile["discipline"],signer))
    return {"slot":item.slot,"apprentice":item.apprentice}

def release(cx, apprentice):
    """复核员撤席：释放后优先让同方向的待补学徒补位，再接新签核。"""
    cx.execute("SELECT code FROM apprentices WHERE code=%s FOR UPDATE",(apprentice,))
    current=cx.execute("DELETE FROM coaching_assignments WHERE apprentice=%s RETURNING slot",(apprentice,)).fetchone()
    if not current:
        raise HTTPException(404,"该学徒没有辅导席")
    filled = _fill_makeup(cx, current["slot"])
    return {"message":"席位已释放", "slot": current["slot"], "makeup_filled": filled}

def close_slot(cx, slot_code, signer, reason=None):
    """导师临时停课：关闭班次，按原签核先后把学徒迁往同方向最近的后续余席。

    未迁出的保留原签核依据进入待补队列。整段在一个事务内完成，行级锁保证与
    签核并发时不超售；已关闭的班次重复提交直接返回现状，不重复迁席。
    """
    slot = cx.execute("SELECT * FROM coaching_slots WHERE code=%s FOR UPDATE", (slot_code,)).fetchone()
    if not slot:
        raise HTTPException(404, "没有这个辅导班次")
    if slot["closed"]:
        return _close_summary(cx, slot_code, repeated=True)
    # 排序口径始终是原签核先后（链式停课时沿用 origin_assigned_at）
    assigned = cx.execute(
        """SELECT * FROM coaching_assignments WHERE slot=%s
           ORDER BY COALESCE(origin_assigned_at, assigned_at), apprentice FOR UPDATE""",
        (slot_code,),
    ).fetchall()
    moved, waiting = [], []
    cx.execute("DELETE FROM coaching_assignments WHERE slot=%s", (slot_code,))
    cx.execute(
        "UPDATE coaching_slots SET closed=true, closed_at=now(), closed_by=%s, closed_reason=%s WHERE code=%s",
        (signer, reason, slot_code),
    )
    for item in assigned:
        # 已被迁过的学徒继续沿用最早的原签核依据，不被本次停课覆盖
        origin_slot = item["origin_slot"] or item["slot"]
        origin_signer = item["origin_signed_by"] or item["signed_by"]
        origin_at = item["origin_assigned_at"] or item["assigned_at"]
        target_code = _nearest_open_seat(cx, item["recommended"], slot["starts_at"])
        if target_code:
            cx.execute(
                """INSERT INTO coaching_assignments
                   (apprentice,slot,recommended,signed_by,assigned_at,origin_slot,origin_signed_by,origin_assigned_at)
                   VALUES (%s,%s,%s,%s,now(),%s,%s,%s)""",
                (item["apprentice"], target_code, item["recommended"], "system:closure",
                 origin_slot, origin_signer, origin_at),
            )
            moved.append({"apprentice": item["apprentice"], "slot": target_code,
                          "origin_slot": origin_slot})
        else:
            cx.execute(
                """INSERT INTO coaching_makeup
                   (apprentice,discipline,origin_slot,origin_signed_by,origin_assigned_at)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (apprentice) DO NOTHING""",
                (item["apprentice"], item["recommended"], origin_slot, origin_signer, origin_at),
            )
            waiting.append({"apprentice": item["apprentice"], "origin_slot": origin_slot})
    return _close_summary(cx, slot_code, moved=moved, waiting=waiting, repeated=False)

def _nearest_open_seat(cx, discipline, after):
    """同方向、晚于停课班次、仍有余席的最近后续班次；锁内复查余量，保证并发不超售。"""
    while True:
        target = cx.execute(
            """SELECT s.code, s.capacity, count(a.apprentice) AS occupied
               FROM coaching_slots s LEFT JOIN coaching_assignments a ON a.slot=s.code
               WHERE s.discipline=%s AND s.closed=false AND s.starts_at > %s
               GROUP BY s.code
               HAVING count(a.apprentice) < s.capacity
               ORDER BY s.starts_at, s.code LIMIT 1""",
            (discipline, after),
        ).fetchone()
        if not target:
            return None
        cx.execute("SELECT code FROM coaching_slots WHERE code=%s FOR UPDATE", (target["code"],))
        occupied = cx.execute(
            "SELECT count(*) AS n FROM coaching_assignments WHERE slot=%s", (target["code"],)
        ).fetchone()["n"]
        if occupied >= target["capacity"]:
            continue  # 并发签核抢先占满，尝试下一个有余席的班次
        return target["code"]

def _close_summary(cx, slot_code, *, moved=None, waiting=None, repeated=False):
    if moved is None:
        moved = cx.execute(
            """SELECT apprentice, slot, origin_slot FROM coaching_assignments
               WHERE origin_slot=%s ORDER BY origin_assigned_at, apprentice""", (slot_code,)
        ).fetchall()
    if waiting is None:
        waiting = cx.execute(
            """SELECT apprentice, origin_slot FROM coaching_makeup
               WHERE origin_slot=%s ORDER BY origin_assigned_at, apprentice""", (slot_code,)
        ).fetchall()
    return {"slot": slot_code, "repeated": repeated, "moved": moved, "waiting": waiting}
