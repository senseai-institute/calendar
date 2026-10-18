"""Download the Swiss Ephemeris data files (planets, Moon, asteroids incl. Chiron).

Covers 1800–2399 CE. Usage: uv run python scripts/fetch_ephemeris.py [dest_dir]
"""

import sys
import urllib.request
from pathlib import Path

from skycal.settings import get_settings

BASE = "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/"
FILES = ["sepl_18.se1", "semo_18.se1", "seas_18.se1"]


def main() -> None:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else get_settings().skycal_ephe_path)
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = dest / name
        if target.exists() and target.stat().st_size > 0:
            print(f"have {target}")
            continue
        print(f"fetch {BASE + name} -> {target}")
        urllib.request.urlretrieve(BASE + name, target)


if __name__ == "__main__":
    main()
