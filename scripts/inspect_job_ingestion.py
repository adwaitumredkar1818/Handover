import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.job import BackgroundJob
from sqlalchemy import select

settings = get_settings()
engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    j = session.execute(select(BackgroundJob).where(BackgroundJob.id == "8d317b14-e714-49b0-948e-82016743ab29")).scalar_one_or_none()
    if j:
        for col in BackgroundJob.__table__.columns:
            print(f"{col.name}: {getattr(j, col.name)}")
