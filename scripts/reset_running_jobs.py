from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from sqlalchemy import text

settings = get_settings()
engine = create_db_engine(settings)
Session = create_session_factory(engine)
with Session() as s:
    res = s.execute(text("UPDATE background_jobs SET status = 'failed', error_message = 'Reset during fast extractor upgrade' WHERE status = 'running'"))
    s.commit()
    print(f"Updated {res.rowcount} running jobs to failed.")
