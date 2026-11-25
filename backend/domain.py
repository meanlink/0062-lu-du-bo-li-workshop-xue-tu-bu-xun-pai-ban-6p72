from pathlib import Path

from fastapi import APIRouter
from roster_api import router as roster
from observations_api import router as observations
from profiles_api import router as profiles
from clinics_api import router as clinics
from profiles import run_job

router = APIRouter(prefix="/api")
router.include_router(roster)
router.include_router(observations)
router.include_router(profiles)
router.include_router(clinics)


def seed(connection):
    connection.execute(Path(__file__).with_name("demo.sql").read_text())
