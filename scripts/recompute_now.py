"""Run the nightly recompute immediately: all entities, default window (+90 days).

uv run python scripts/recompute_now.py
"""

import logging

from sqlmodel import Session

from skycal.db.session import get_engine, migrate
from skycal.jobs.recompute import recompute_all

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    migrate()
    with Session(get_engine()) as session:
        counts = recompute_all(session)
    print(f"recomputed {len(counts)} entities, {sum(counts.values())} events")
