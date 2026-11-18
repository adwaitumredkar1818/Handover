from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from sqlalchemy import text

s = create_session_factory(create_db_engine(get_settings()))()
try:
    sql = """
    UPDATE evidence_chunks 
    SET search_vector = setweight(to_tsvector('english', coalesce(chunk_text, '')), 'A') || 
                       setweight(to_tsvector('simple', coalesce(chunk_text, '')), 'B')
    WHERE search_vector IS NULL;
    """
    res = s.execute(text(sql))
    s.commit()
    print("Updated search_vector for rows:", res.rowcount)
finally:
    s.close()
