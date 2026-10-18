"""Eclipses.

A solar eclipse is a New Moon near a lunar node; a lunar eclipse is a Full
Moon near a node. Tier 1 when the eclipse degree conjoins/opposes a natal
point.

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class EclipseGenerator(NotYetImplemented):
    technique = Technique.eclipse
