import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import get_settings, _REPO_ROOT
from app.services.storage import LocalPrivateStorageBackend, validate_storage_object_key

settings = get_settings()
key = "8fc2aebc-69ea-4c87-90bf-1c377ab249b4/a79345eb-0464-4c8a-bb40-bbce15e9a206/02d63dd9-43ce-4113-95d4-7e2e35bcb7ba.enc"
norm = validate_storage_object_key(key)

candidates = [
    _REPO_ROOT / "backend" / "data" / "uploads" / norm,
    _REPO_ROOT / "data" / "uploads" / norm,
    Path.cwd() / "backend" / "data" / "uploads" / norm,
    Path.cwd() / "data" / "uploads" / norm,
]
for c in candidates:
    print(f"Candidate: {c} -> Exists: {c.exists()}")
