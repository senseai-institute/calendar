from pathlib import Path

import pytest

from skycal.settings import get_settings


def pytest_sessionstart(session):
    ephe = Path(get_settings().skycal_ephe_path)
    if not (ephe / "seas_18.se1").exists():
        pytest.exit(
            f"Swiss Ephemeris files missing in {ephe}. "
            "Run `uv run python scripts/fetch_ephemeris.py` first.",
            returncode=2,
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """API client on a fresh, migrated SQLite database, scheduler off."""
    from fastapi.testclient import TestClient

    from skycal.db.session import get_engine

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("API_KEY", "")  # ignore any key in a local .env
    get_settings.cache_clear()
    get_engine.cache_clear()
    from skycal.api.app import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    get_engine.cache_clear()
