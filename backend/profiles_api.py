from fastapi import APIRouter,Depends
from core import db,enqueue,require
from profiles import list_profiles

router=APIRouter(prefix="/profiles")

@router.get("")
def profiles(_=Depends(require())):
    with db() as cx:
        return list_profiles(cx)

@router.post("/{apprentice}")
def request_profile(apprentice:str,_=Depends(require("operator","reviewer"))):
    with db() as cx:
        return {"job_id":enqueue(cx,"classroom-profile",{"apprentice":apprentice})}
