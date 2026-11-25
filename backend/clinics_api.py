from fastapi import APIRouter,Depends,HTTPException
from core import db,require
from clinic_assignments import Assignment,sign

router=APIRouter(prefix="/clinics")

@router.get("")
def schedules(_=Depends(require())):
    with db() as cx:
        slots=cx.execute("SELECT s.*,count(a.apprentice) AS occupied FROM coaching_slots s LEFT JOIN coaching_assignments a ON a.slot=s.code GROUP BY s.code ORDER BY starts_at").fetchall()
        assignments=cx.execute("SELECT c.*,a.name FROM coaching_assignments c JOIN apprentices a ON c.apprentice=a.code ORDER BY c.slot,a.code").fetchall()
        return {"slots":slots,"assignments":assignments}

@router.post("/assign")
def add(item:Assignment,user=Depends(require("reviewer"))):
    with db() as cx:
        return sign(cx,item,user["email"])

@router.post("/{apprentice}/release")
def release(apprentice:str,_=Depends(require("reviewer"))):
    with db() as cx:
        cx.execute("SELECT code FROM apprentices WHERE code=%s FOR UPDATE",(apprentice,))
        if not cx.execute("DELETE FROM coaching_assignments WHERE apprentice=%s RETURNING slot",(apprentice,)).fetchone():
            raise HTTPException(404,"该学徒没有辅导席")
        return {"message":"席位已释放"}
