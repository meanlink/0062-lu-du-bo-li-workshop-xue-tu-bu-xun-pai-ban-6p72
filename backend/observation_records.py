from datetime import date
from pydantic import BaseModel, Field

class Observation(BaseModel):
    code: str = Field(pattern=r"^O-[0-9]{3,7}$")
    apprentice: str
    noted_on: date
    setup: int = Field(ge=0,le=10)
    handoff: int = Field(ge=0,le=10)
    teardown: int = Field(ge=0,le=10)
    source: str = Field(min_length=2,max_length=80)

def observations(cx):
    return cx.execute('''
        SELECT o.*, a.name FROM skill_observations o LEFT JOIN apprentices a ON o.apprentice=a.code
        ORDER BY noted_on DESC, code
    ''').fetchall()
