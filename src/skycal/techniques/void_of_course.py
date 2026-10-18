"""Void-of-course Moon.

The interval from the Moon's last major aspect (to any planet, using the five
Ptolemaic aspects) while in a sign, until it enters the next sign. Traditionally
a 'nothing comes of it' period. Tier 4. Sky-wide, so events have no entity.

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class VoidOfCourseGenerator(NotYetImplemented):
    technique = Technique.void_of_course
