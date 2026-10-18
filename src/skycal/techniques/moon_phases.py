"""Moon phases.

The phase is the Moon–Sun angle: 0° new, 90° first quarter, 180° full,
270° last quarter. Tier 4.

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class MoonPhaseGenerator(NotYetImplemented):
    technique = Technique.moon_phase
