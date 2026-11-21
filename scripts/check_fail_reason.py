import sys
import os
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
from app.models.evidence import EvidenceItem
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

ev_id = uuid.UUID("b7d0bb4a-ab02-488e-b784-bbfd625144ce")

with session_factory() as session:
    ev = session.execute(select(EvidenceItem).where(EvidenceItem.id == ev_id)).scalar_one()
    print(f"Evidence error: {ev.error_message}")
    job = session.execute(select(BackgroundJob).where(BackgroundJob.evidence_id == ev_id)).scalar_one_or_none()
    if job:
        print(f"Job error_code: {job.error_code}, error_message: {job.error_message}")
