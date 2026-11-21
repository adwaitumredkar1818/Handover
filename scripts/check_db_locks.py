import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.db.session import create_db_engine
from app.core.config import get_settings
from sqlalchemy import text

settings = get_settings()
engine = create_db_engine(settings)
with engine.connect() as conn:
    rows = conn.execute(text("SELECT pid, state, wait_event_type, wait_event, query FROM pg_stat_activity WHERE state != 'idle' and query NOT LIKE '%pg_stat_activity%';")).fetchall()
    print(f"Active queries: {len(rows)}")
    for r in rows:
        print(f"PID {r[0]} | state: {r[1]} | wait: {r[2]}:{r[3]} | query: {r[4][:80]}")
