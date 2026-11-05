"""Named projection of the verified original 0x610 state.

The old codec's `pages` field is a byte-keyed allocation-group map. The
consumer flattens every group for the current character; it is not evidence
of independent character pages. Actual page selector/count are tail bytes.
All unresolved state remains explicit. This constructs no initial defaults.
"""
from dataclasses import dataclass
from els_server.protocol.resonance_2026 import ResonanceState

# TEMPORARY field probe - delete once the ERP point field is identified.
# The client shows an available-point counter but renders 0 even though the
# real budget travels in field0c, and it never sends 0x611 (no "+" appears).
# Only level and enabled have verified meanings in this DTO, so distinct
# sentinels are stamped into the remaining scalar candidates: whichever value
# appears in the game's point counter is the field the client actually reads.
PROBE = {'field21': 222, 'field32': 111}


@dataclass(frozen=True)
class ResonanceCharacterState:
    level: int
    cumulative_experience: int
    available_points: int
    enabled: bool
    allocation_groups: tuple
    field21: int
    field25: int
    field29: int
    field31: int
    field32: int
    selected_page: int
    page_count: int

    def notice(self):
        """Reuse the proven encoder without changing order or opaque fields."""
        probe = PROBE or {}
        return ResonanceState(
            level=self.level,field04=self.cumulative_experience,
            field0c=probe.get('field0c',self.available_points),enabled=self.enabled,
            pages=self.allocation_groups,field21=probe.get('field21',self.field21),
            field25=probe.get('field25',self.field25),
            field29=self.field29,field31=self.field31,
            field32=probe.get('field32',self.field32),
            field3a=self.selected_page,field3b=self.page_count).notice()
