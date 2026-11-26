"""
conftest.py — Shared test fixtures for Phantom E2E tests.

Provides:
  - Isolated test database (not production chat_history.db)
  - QApplication instance for UI tests
  - LLM pipeline access for both Groq and Local AI modes
  - Cleanup hooks
"""
import os
import sys
import pytest
import tempfile
import shutil

# Ensure project root is on the path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ── Isolated test database ─────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def test_db_dir():
    """Create a temporary directory for the test database."""
    tmpdir = tempfile.mkdtemp(prefix="phantom_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db(test_db_dir):
    """
    Redirect storage to use a test database instead of production.
    This is session-scoped so ALL tests share one test DB.
    """
    from storage import storage
    original_db_path = storage.DB_PATH
    storage.DB_PATH = os.path.join(test_db_dir, "test_chat_history.db")
    storage.init_db()
    yield
    storage.DB_PATH = original_db_path


@pytest.fixture
def fresh_chat():
    """Create a fresh chat and return its ID. Cleaned up after test."""
    from storage import storage
    from llm import clear_session
    chat_id = storage.create_chat("Test Chat")
    clear_session(chat_id)
    yield chat_id
    try:
        clear_session(chat_id)
        storage.delete_chat(chat_id)
    except Exception:
        pass


# ── QApplication for UI tests ──────────────────────────────────────────────────
@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for UI tests. Only one can exist per process."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ── Helpers ────────────────────────────────────────────────────────────────────
@pytest.fixture
def groq_available():
    """Check if Groq API is available (key is set)."""
    from llm import GROQ_API_KEY
    return bool(GROQ_API_KEY and GROQ_API_KEY != "no_key_set")


@pytest.fixture
def ollama_available():
    """Check if Ollama is running locally."""
    import requests
    from llm import OLLAMA_BASE_URL
    try:
        base = OLLAMA_BASE_URL.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        resp = requests.get(base, timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


# ── Destructive tool skip list ─────────────────────────────────────────────────
SKIP_DESTRUCTIVE_TOOLS = {
    "shutdown_pc", "restart_pc", "logoff_user", "lock_pc",
    "sleep_pc", "empty_recycle_bin"
}
