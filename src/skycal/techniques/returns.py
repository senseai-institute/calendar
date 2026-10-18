"""Solar and lunar returns.

solar return  the moment each year the Sun comes back to its exact natal
              longitude (~birthday); a chart cast then is read for the year ahead.
lunar return  the same for the Moon, every ~27.3 days, read for the month ahead.


Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class SolarReturnGenerator(NotYetImplemented):
    technique = Technique.solar_return


class LunarReturnGenerator(NotYetImplemented):
    technique = Technique.lunar_return
