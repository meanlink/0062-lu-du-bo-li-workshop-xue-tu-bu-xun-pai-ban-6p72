from fastapi import APIRouter,Depends,HTTPException
from core import db,require
from observation_records import Observation, observations

router=APIRouter(prefix="/observations")

@router.get("")
def view(_=Depends(require())):
    with db() as cx:
        return observations(cx)

@router.post("")
def record(item:Observation,_=Depends(require("operator","reviewer"))):
    with db() as cx:
        person=cx.execute("SELECT eligible FROM apprentices WHERE code=%s FOR UPDATE",(item.apprentice,)).fetchone()
        if not person or not person["eligible"]:
            raise HTTPException(409,"学徒当前不在本轮训练")
        if cx.execute("SELECT 1 FROM coaching_assignments WHERE apprentice=%s",(item.apprentice,)).fetchone():
            raise HTTPException(409,"辅导名单已提交，撤销后可追加观察")
        cx.execute('''
        INSERT INTO skill_observations(code,apprentice,noted_on,setup,handoff,teardown,source)
        VALUES(%(code)s,%(apprentice)s,%(noted_on)s,%(setup)s,%(handoff)s,%(teardown)s,%(source)s)
        ''',item.model_dump())
        return {"code":item.code}
