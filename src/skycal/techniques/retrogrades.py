"""Retrograde stations.

A station is the moment a planet's longitude speed crosses zero: stationing
retrograde (starts moving backwards) or direct (resumes forward motion).
Planets linger near the station degree, so it is emphasised. Tier 3.

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class RetrogradeGenerator(NotYetImplemented):
    technique = Technique.retrograde
