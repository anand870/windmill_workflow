import sys
import os
import pytest

# Add workspace root so `from f.gold.gold_utils import ...` resolves
WORKSPACE_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, WORKSPACE_ROOT)

# Load .env from workspace root so API keys are available in live tests
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(WORKSPACE_ROOT, ".env"))
except ImportError:
    pass  # dotenv not installed — keys must be set in the shell environment


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: marks tests that hit real external URLs (run alongside unit tests by default)",
    )
