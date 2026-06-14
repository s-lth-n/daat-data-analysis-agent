"""
conftest.py — Place this in ~/ta-data-analyst/tests/
Automatically adds backend/ to Python path so tests can import tools, agents, etc.
"""

import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))
