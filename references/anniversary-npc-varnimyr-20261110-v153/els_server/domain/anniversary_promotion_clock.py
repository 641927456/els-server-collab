"""Observe the same authenticated sessions as the existing online activities."""
from els_server.domain.anniversary_promotion import CAMPAIGN, ENDS, STARTS
from els_server.domain.anniversary_exchange import MAX_COUPONS
from els_server.domain.attendance_2026_online import selected_local_test_character
from els_server.domain.online_2026_clock import OnlineTitleClock
from els_server.storage.anniversary_promotion import coupons_issued, record_online
from els_server.storage.read_scope import snapshot_connection


class AnniversaryPromotionClock(OnlineTitleClock):
    def __init__(self, *, monotonic, epoch):
        super().__init__(None, campaign=CAMPAIGN, eligibility=self._eligible,
                         monotonic=monotonic, epoch=epoch)
        self.check_receipt_at = 0

    def observe(self, session, *, stop=False):
        now = self.epoch()
        if now >= STARTS:
            super().observe(session, stop=stop or now >= ENDS)

    def _eligible(self, session):
        identity = selected_local_test_character(session)
        if identity is None or identity[3] < 99:
            return None
        now = self.monotonic()
        if now >= self.check_receipt_at:
            path, account, _, _ = identity
            with snapshot_connection(path) as db:
                self.closed = coupons_issued(db, account) == MAX_COUPONS
            self.check_receipt_at = now + 15
            if self.closed:
                return None
        return identity

    def _write_spans(self, db, account, character, start, end):
        record_online(db, account=account, character=character, start=start, end=end)
