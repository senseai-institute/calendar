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
