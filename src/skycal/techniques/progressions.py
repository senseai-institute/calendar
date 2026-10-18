"""Secondary progressions: "a day for a year".

The sky N days after birth stands for the person at age N years: progressed
planets are computed at birth_jd + age_in_years days, then aspected to the natal
chart. The progressed Moon moves ~1° per month; the progressed Sun ~1° per year.

Phase 3. Stubbed so the `EventGenerator` slot exists.
"""

from skycal.db.models import Technique
from skycal.techniques.base import NotYetImplemented


class ProgressionGenerator(NotYetImplemented):
    technique = Technique.progression
