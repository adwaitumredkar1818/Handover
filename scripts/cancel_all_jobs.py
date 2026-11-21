from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import create_db_engine

settings = get_settings()
engine = create_db_engine(settings)

with engine.begin() as conn:
    res = conn.execute(
        text("UPDATE background_jobs SET status = 'cancelled', error_message = 'Cancelled by user request' WHERE status IN ('running', 'queued')")
    )
    print(f"Committed cancellation of {res.rowcount} background jobs.")
