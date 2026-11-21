"""Convenience wrapper for Stage 1 Deterministic Knowledge Bootstrap."""

import os
import sys

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.scripts.bootstrap_project_knowledge import main

if __name__ == "__main__":
    main()
