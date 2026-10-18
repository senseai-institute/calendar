"""Vimshottari dasha: the Vedic 120-year planetary period system.

Life is divided into periods (maha-dashas) ruled in turn by Ketu 7y, Venus 20,
Sun 6, Moon 10, Mars 7, Rahu 18, Jupiter 16, Saturn 19, Mercury 17 years. The
starting period is the lord of the natal Moon's nakshatra, with the balance set
by how far through that nakshatra the Moon is. Each period nests sub-periods
(antar-dashas) in the same proportions. A dasha change is a tier-1 event.

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class DashaGenerator(NotYetImplemented):
    technique = Technique.dasha
