from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel, Field
from core import db,require
from clinic_assignments import Assignment,close_slot,release,sign

router=APIRouter(prefix="/clinics")

@router.get("")
def schedules(_=Depends(require())):
    with db() as cx:
        slots=cx.execute("SELECT s.*,count(a.apprentice) AS occupied FROM coaching_slots s LEFT JOIN coaching_assignments a ON a.slot=s.code GROUP BY s.code ORDER BY starts_at").fetchall()
        assignments=cx.execute("""
            SELECT c.*,a.name FROM coaching_assignments c JOIN apprentices a ON a.code=c.apprentice
            ORDER BY c.slot,a.code""").fetchall()
        makeup=cx.execute("""
            SELECT m.*,a.name FROM coaching_makeup m JOIN apprentices a ON a.code=m.apprentice
            ORDER BY m.origin_assigned_at,m.apprentice""").fetchall()
        return {"slots":slots,"assignments":assignments,"makeup":makeup}

@router.post("/assign")
def add(item:Assignment,user=Depends(require("reviewer"))):
    with db() as cx:
        return sign(cx,item,user["email"])

@router.post("/{apprentice}/release")
def release_seat(apprentice:str,_=Depends(require("reviewer"))):
    with db() as cx:
        return release(cx,apprentice)

class Closure(BaseModel):
    reason: str | None = Field(default=None, max_length=200)

@router.post("/{slot_code}/close")
def close(slot_code:str,item:Closure,user=Depends(require("reviewer"))):
    reason = (item.reason or "").strip() or None
    with db() as cx:
        return close_slot(cx,slot_code,user["email"],reason)
