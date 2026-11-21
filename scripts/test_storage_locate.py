import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import get_settings
from app.services.storage import LocalPrivateStorageBackend

settings = get_settings()
print(f"settings.storage.upload_storage_path: {settings.storage.upload_storage_path}")

storage = LocalPrivateStorageBackend(
    root_path=settings.storage.upload_storage_path,
    file_encryption_key=settings.security.file_encryption_key.get_secret_value(),
)
print(f"storage.root_path: {storage.root_path}")

key = "8fc2aebc-69ea-4c87-90bf-1c377ab249b4/a79345eb-0464-4c8a-bb40-bbce15e9a206/02d63dd9-43ce-4113-95d4-7e2e35bcb7ba.enc"
loc = storage._locate_existing_file(key)
print(f"Located file: {loc}")
if loc:
    print(f"Exists: {loc.exists()}, size: {loc.stat().st_size}")
