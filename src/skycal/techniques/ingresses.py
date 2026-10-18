"""Ingresses.

An ingress is a planet entering a new sign (crossing a multiple of 30°).

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class IngressGenerator(NotYetImplemented):
    technique = Technique.ingress
