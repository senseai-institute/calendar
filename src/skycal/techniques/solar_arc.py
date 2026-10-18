"""Solar arc directions.

Every natal point is advanced by the same arc: the distance the progressed Sun
has moved since birth (~1°/year). Directed points are then aspected to natal.

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class SolarArcGenerator(NotYetImplemented):
    technique = Technique.solar_arc
