import traceback
from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models.assistant import AssistantMessage
from sqlalchemy import select, text

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    messages = s.scalars(select(AssistantMessage).where(text("structured_payload_json->>'investigation_id' IS NOT NULL"))).all()
    print(f"Total matching messages: {len(messages)}")
    for m in messages:
        print("Msg ID:", m.id)
        print("Investigation ID in payload:", m.structured_payload_json.get("investigation_id") if isinstance(m.structured_payload_json, dict) else "NOT DICT")
finally:
    s.close()
