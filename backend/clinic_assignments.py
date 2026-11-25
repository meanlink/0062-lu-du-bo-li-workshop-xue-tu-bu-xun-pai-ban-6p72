from fastapi import HTTPException
from pydantic import BaseModel

class Assignment(BaseModel):
    apprentice: str
    slot: str

def sign(cx,item,signer):
    student=cx.execute("SELECT eligible FROM apprentices WHERE code=%s FOR UPDATE",(item.apprentice,)).fetchone()
    choice=cx.execute("SELECT * FROM coaching_slots WHERE code=%s FOR UPDATE",(item.slot,)).fetchone()
    profile=cx.execute("SELECT * FROM apprentice_profiles WHERE apprentice=%s",(item.apprentice,)).fetchone()
    if not student or not student["eligible"] or not choice or not profile:
        raise HTTPException(409,"需确认轮训资格并先计算补训方向")
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
