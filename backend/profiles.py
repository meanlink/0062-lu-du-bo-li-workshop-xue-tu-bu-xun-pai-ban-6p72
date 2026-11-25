from fastapi import HTTPException
from psycopg.types.json import Jsonb
from discriminant import classify

def list_profiles(cx):
    return cx.execute('''
        SELECT p.*,a.name FROM apprentice_profiles p JOIN apprentices a ON p.apprentice=a.code
        ORDER BY p.margin DESC,a.code
    ''').fetchall()

def run_job(cx,kind,payload):
    if kind != "classroom-profile":
        raise ValueError("Worker task type")
    code=payload["apprentice"]
    person=cx.execute("SELECT eligible FROM apprentices WHERE code=%s FOR UPDATE",(code,)).fetchone()
    if not person or not person["eligible"]:
        raise HTTPException(409,"名单变化，课堂补训测算停止")
    row=cx.execute("SELECT * FROM skill_observations WHERE apprentice=%s ORDER BY noted_on DESC, code DESC LIMIT 1",(code,)).fetchone()
    if not row:
        raise HTTPException(409,"没有课堂观察")
    if cx.execute("SELECT 1 FROM coaching_assignments WHERE apprentice=%s",(code,)).fetchone():
        raise HTTPException(409,"分类已用于排班，请先撤销席位")
    anchors=cx.execute("SELECT * FROM skill_observations WHERE label IS NOT NULL ORDER BY code").fetchall()
    result=classify(anchors,row)
    cx.execute('''
        INSERT INTO apprentice_profiles(apprentice,discipline,n_distinct,margin,drivers,observation)
        VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(apprentice) DO UPDATE SET
        discipline=EXCLUDED.discipline,n_distinct=EXCLUDED.n_distinct,margin=EXCLUDED.margin,
        drivers=EXCLUDED.drivers,observation=EXCLUDED.observation,computed_at=now()
    ''',(code,result["discipline"],result["n_distinct"],result["margin"],Jsonb(result["drivers"]),row["code"]))
    return result | {"observation":row["code"]}
