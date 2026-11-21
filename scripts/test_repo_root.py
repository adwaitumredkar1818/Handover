import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core import config

print(f"_REPO_ROOT: {config._REPO_ROOT}")
print(f"backend/data/uploads exists: {(config._REPO_ROOT / 'backend' / 'data' / 'uploads').exists()}")
print(f"data/uploads exists: {(config._REPO_ROOT / 'data' / 'uploads').exists()}")
