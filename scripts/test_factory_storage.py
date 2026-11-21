import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import get_settings
from app.services.storage_factory import build_storage_backend

settings = get_settings()
storage = build_storage_backend(settings)
print(f"storage.root_path: {storage.root_path}")
key = "8fc2aebc-69ea-4c87-90bf-1c377ab249b4/a79345eb-0464-4c8a-bb40-bbce15e9a206/02d63dd9-43ce-4113-95d4-7e2e35bcb7ba.enc"
print(f"locate: {storage._locate_existing_file(key)}")
