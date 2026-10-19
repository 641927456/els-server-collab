"""Opt-in, per-connection projection of committed online progress to 2AF.

The caller supplies the verified activity record and scene eligibility, flushes
the online clock first, and calls clear before losing eligibility/disconnecting.
No original campaign ID, flag, reward preview or maintenance time is invented.
The emitter must synchronously accept each ordered event or raise. A new
connection must use a new instance; cached UI state is never persisted.
"""
from dataclasses import replace
from els_server.protocol.access_event_2026 import ActivityRecord, activity_list_update
from els_server.storage.online_2026_progress import OnlineTitleProgress


class OnlineTitleDisplay:
    def __init__(self):
        self._record = self._context = self._shape = self._anchor = None
        self._busy = False

    def _remove(self, emit):
        if self._record is None:
            return 0
        emit(activity_list_update(action=2, records=(self._record,)))
        self._record = self._context = self._shape = self._anchor = None
        return 1

    def clear(self, emit):
        """Remove only this instance's last accepted row; repeated clear is empty."""
        if self._busy:
            raise RuntimeError('Reentrant online display update')
        if not callable(emit):
            raise TypeError('Ordered synchronous emitter required')
        self._busy = True
        try:
            return self._remove(emit)
        finally:
            self._busy = False

    def synchronize(self, repo, *, account, character, week, now, record, emit):
        """Publish remaining seconds/60, never the original full-duration value.

        Normal committed accrual follows the client's own countdown without
        another upsert, which would reset its clock and rearm its notification.
        Missing accrual or a clock discontinuity triggers a correction. A changed
        role/week always refreshes it even when both have the same remaining
        duration. The client countdown reaches zero without an extra upsert: reward delivery and subsequent icon removal are separate
        unverified policy, not inferred from reaching the time threshold.
        """
        if self._busy:
            raise RuntimeError('Reentrant online display update')
        if not isinstance(repo, OnlineTitleProgress) or type(record) is not ActivityRecord:
            raise TypeError('Verified progress repository and explicit activity record required')
        if type(now) is not int or not 0 <= now < 2**63 or not callable(emit):
            raise ValueError('Integer server time and ordered emitter required')
        if repo.db.in_transaction:
            raise RuntimeError('Uncommitted activity progress cannot be advertised')
        record.encode()  # Validate all supplied fields, including unknown ones.
        self._busy = True
        try:
            # One read snapshot; never commit or change caller/player data.
            repo.db.execute('BEGIN')
            try:
                level = repo._owner(account, character)
                lo, hi = repo._period(week)
                snapshot = repo.snapshot(account=account, character=character, week=week)
            finally:
                repo.db.rollback()
            if level < 10 or not lo <= now < hi:
                return self._remove(emit)
            current = replace(record, float_28=snapshot['remaining_seconds']/60)
            shape = replace(current, float_28=0.).encode()
            remaining = snapshot['remaining_seconds']
            context = (repo.campaign, account, character, week)
            if self._context == context and self._shape == shape:
                anchor_time, anchor_remaining = self._anchor
                if now >= anchor_time and remaining == max(0, anchor_remaining-(now-anchor_time)):
                    return 0
            sent = 0
            if self._record is not None and self._record.key != current.key:
                sent += self._remove(emit)
            emit(activity_list_update(action=1, records=(current,)))
            # If the emitter raises, retain the last accepted state for retry.
            self._record, self._context, self._shape = current, context, shape
            self._anchor = (now, remaining)
            return sent+1
        finally:
            self._busy = False
