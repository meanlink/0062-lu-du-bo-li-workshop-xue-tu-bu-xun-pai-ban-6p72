from fastapi import APIRouter, Depends
from core import db, require
from roster import roster, toggle, Enrollment

router = APIRouter(prefix="/apprentices")


@router.get("")
def view(_=Depends(require())):
    with db() as cx:
        return roster(cx)


@router.post("/{code}/eligibility")
def update(code: str, changes: Enrollment, _=Depends(require("reviewer"))):
    with db() as cx:
        return toggle(cx, code, changes.eligible)
