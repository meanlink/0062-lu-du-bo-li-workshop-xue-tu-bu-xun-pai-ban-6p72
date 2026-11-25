from fastapi import HTTPException
from pydantic import BaseModel

class Enrollment(BaseModel):
    eligible: bool

def roster(cx):
    return cx.execute('''
        SELECT a.*, count(o.code) AS observations, s.discipline AS recommendation
        FROM apprentices a LEFT JOIN skill_observations o ON o.apprentice=a.code
        LEFT JOIN apprentice_profiles s ON s.apprentice=a.code
        GROUP BY a.code,s.discipline ORDER BY a.code
    ''').fetchall()

def toggle(cx, code, eligible):
    student = cx.execute("SELECT code FROM apprentices WHERE code=%s FOR UPDATE", (code,)).fetchone()
    if student is None:
        raise HTTPException(404,"找不到学徒")
    if not eligible and cx.execute("SELECT 1 FROM coaching_assignments WHERE apprentice=%s",(code,)).fetchone():
        raise HTTPException(409,"已有辅导席位，请先撤销指派再退出轮训")
    cx.execute("UPDATE apprentices SET eligible=%s WHERE code=%s",(eligible,code))
    return {"eligible":eligible}
