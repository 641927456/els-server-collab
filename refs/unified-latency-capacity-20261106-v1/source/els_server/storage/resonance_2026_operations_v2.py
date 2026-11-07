"""Current-client page route; supersedes v1's unbound0x614 selection method.

Positive0x611/612 logic remains. Page-tab selection now uses0x79E/79F, with
the complete explicit period/opaque fields that its original consumer reads.
"""
from dataclasses import dataclass
from els_server.storage.resonance_2026_operations import ResonanceOperations
from els_server.protocol.resonance_2026_page_switch import page_switch_request, page_switch_reply
from els_server.protocol.resonance_2026_state import ResonanceCharacterState


@dataclass(frozen=True)
class ResonanceOpaqueFields:
    field21: int
    field25: int
    field29: int
    field31: int
    field32: int


class ResonanceOperationsV2(ResonanceOperations):
    def allocate(self, *, account, character, operation, expected_revision,
                 payload, bonus_points, result, trailing_value):
        # Only the verified success code may accompany an actual point mutation.
        if type(result) is not int or result != 0:
            raise ValueError('Successful mutation requires original result0')
        return super().allocate(account=account, character=character,
            operation=operation, expected_revision=expected_revision,
            payload=payload, bonus_points=bonus_points, result=0,
            trailing_value=trailing_value)

    def select(self, *, account, character, operation, expected_revision,
               payload, opaque_fields):
        """Original page-tab route; verified scene eligibility remains caller-owned.

        Opaque fields must come from authoritative current state, never a guessed
        zero/default or the client's page-only request. Outer transactions retain
        commit ownership and must delay transmitting the provisional response.
        """
        selected_page = page_switch_request(payload)
        if type(opaque_fields) is not ResonanceOpaqueFields:
            raise ValueError('Explicit authoritative opaque fields required')
        with self.pages.transaction():
            self.pages.select(account=account, character=character,
                operation=operation, expected_revision=expected_revision,
                selected_page=selected_page)
            progress = self.accounts.snapshot(account=account, character=character)
            current = self.pages.snapshot(account=account, character=character)
            if progress is None or current is None:
                raise ValueError('Authoritative resonance state missing')
            grouped = {}
            for stat, points in current.selected().points:
                grouped.setdefault(self.pages.rules.stat(stat).tab, []).append((stat, points))
            state = ResonanceCharacterState(
                level=progress.level, cumulative_experience=progress.cumulative_experience,
                available_points=current.selected().available_points, enabled=current.enabled,
                allocation_groups=tuple((tab, tuple(values)) for tab, values in sorted(grouped.items())),
                field21=opaque_fields.field21, field25=opaque_fields.field25,
                field29=opaque_fields.field29, field31=opaque_fields.field31,
                field32=opaque_fields.field32, selected_page=current.selected_page,
                page_count=len(current.pages))
            event = page_switch_reply(result=0, state=state)
        return event
