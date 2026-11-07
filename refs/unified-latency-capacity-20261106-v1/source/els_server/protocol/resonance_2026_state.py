"""Named projection of the verified original 0x610 state.

The old codec's `pages` field is a byte-keyed allocation-group map. The
consumer flattens every group for the current character; it is not evidence
of independent character pages. Actual page selector/count are tail bytes.
All unresolved state remains explicit. This constructs no initial defaults.
"""
from dataclasses import dataclass
from els_server.protocol.resonance_2026 import ResonanceState


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
        return ResonanceState(
            level=self.level,field04=self.cumulative_experience,
            field0c=self.available_points,enabled=self.enabled,
            pages=self.allocation_groups,field21=self.field21,field25=self.field25,
            field29=self.field29,field31=self.field31,field32=self.field32,
            field3a=self.selected_page,field3b=self.page_count).notice()
