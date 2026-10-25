"""Atomic local resonance edits and their fresh committed-state replies.

Caller must verify authenticated gameplay state, original eligibility and
stable operation identity. No transport endpoint or default initialization.
"""
from els_server.storage.resonance_2026_progress import AccountResonance
from els_server.storage.resonance_2026_pages import ResonancePages
from els_server.protocol.resonance_2026_reply import snapshot_reply


class ResonanceOperations:
    def __init__(self, connection, curve, original_definition):
        self.accounts = AccountResonance(connection, curve)
        self.pages = ResonancePages(connection, original_definition)
        self.original_definition = original_definition

    def _reply(self, kind, account, character, result, trailing_value):
        # Re-read current state, not a possibly historical idempotency receipt.
        progress = self.accounts.snapshot(account=account, character=character)
        pages = self.pages.snapshot(account=account, character=character)
        if progress is None or pages is None:
            raise ValueError('Authoritative resonance state missing')
        return snapshot_reply(kind=kind, result=result, progress=progress,
            page_state=pages, original_definition=self.original_definition,
            trailing_value=trailing_value, inventory_updates=())

    def allocate(self, *, account, character, operation, expected_revision,
                 payload, bonus_points, result, trailing_value):
        """Reply is returned after commit, or provisional in a caller transaction.

        Encoding failure rolls back both points and receipt. Positive allocation
        has no inventory changes; negative deltas fail in the verified planner.
        Result and opaque tail remain explicit until original callers supply them.
        """
        with self.pages.transaction():
            self.pages.allocate(account=account, character=character,
                operation=operation, expected_revision=expected_revision,
                payload=payload, bonus_points=bonus_points)
            event = self._reply(0x612, account, character, result, trailing_value)
        return event

    def select(self, *, account, character, operation, expected_revision,
               selected_page, result, trailing_value):
        """Storage selection only; gameplay gates belong to verified callers."""
        with self.pages.transaction():
            self.pages.select(account=account, character=character,
                operation=operation, expected_revision=expected_revision,
                selected_page=selected_page)
            event = self._reply(0x614, account, character, result, trailing_value)
        return event
