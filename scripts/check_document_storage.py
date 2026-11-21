import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.session import create_db_engine, create_session_factory
from app.core.config import get_settings
from app.models.evidence import EvidenceItem
from sqlalchemy import select

settings = get_settings()
print(f"STORAGE PROVIDER: {settings.storage.provider}")
print(f"upload_storage_path: {settings.storage.upload_storage_path}")

engine = create_db_engine(settings)
session_factory = create_session_factory(engine)

with session_factory() as session:
    ev = session.execute(select(EvidenceItem).where(EvidenceItem.id == "b7d0bb4a-ab02-488e-b784-bbfd625144ce")).scalar_one_or_none()
    if ev:
        print(f"Evidence: {ev.title}")
        print(f"storage_object_key: {ev.storage_object_key}")
        print(f"storage_envelope_key_id: {ev.storage_envelope_key_id}")
        print(f"file_size_bytes: {ev.file_size_bytes}")
        print(f"content_hash: {ev.content_hash}")
        print(f"processing_status: {ev.processing_status}")
        print(f"error_message: {ev.error_message}")

        if settings.storage.provider == "local_encrypted":
            full_path = os.path.join(str(settings.storage.upload_storage_path), ev.storage_object_key)
            print(f"Local file expected path: {full_path}")
            print(f"File exists: {os.path.exists(full_path)}")
            # Let's also search where on disk ev.storage_object_key might exist
            for root, dirs, files in os.walk("."):
                if ev.storage_object_key in files:
                    print(f"FOUND ON DISK: {os.path.join(root, ev.storage_object_key)}")
