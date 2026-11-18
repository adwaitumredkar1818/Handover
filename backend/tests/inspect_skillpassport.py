from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem, EvidenceChunk
from sqlalchemy import select
import uuid

settings = get_settings()
engine = create_db_engine(settings)
sf = create_session_factory(engine)
s = sf()
try:
    p_id = uuid.UUID("ed33c53a-7678-4d5b-8212-64c233897142")
    items = s.scalars(select(EvidenceItem).where(EvidenceItem.project_id == p_id)).all()
    print(f"Skillpassport evidence items count: {len(items)}")
    for it in items[:10]:
        print(f"  - Item: {it.id} | Provider: {it.source_provider} | Title: {it.title} | Extracted Text Len: {len(it.extracted_text) if it.extracted_text else 0}")
finally:
    s.close()
