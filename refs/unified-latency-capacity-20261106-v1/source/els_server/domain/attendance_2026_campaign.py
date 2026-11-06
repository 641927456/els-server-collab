"""Compose proven task awards with authoritative session time/clear facts.

Explicit local configuration supplies the scene policy and schedule. This
does not invent daily carry/autoaccept or a BA8 target-selection policy.
"""
from els_server.domain.attendance_2026_award_flow import AttendanceAwardFlow
from els_server.domain.attendance_2026_clear import AttendanceClearBinding
from els_server.domain.attendance_2026_online import AttendanceOnlineClock
from els_server.game_data import client_data


class AttendanceCampaign(AttendanceAwardFlow):
    def __init__(self,definition,*,eligibility,monotonic,epoch,**options):
        super().__init__(definition,**options)
        self.online=AttendanceOnlineClock(definition,campaign=self.campaign,definition_sha256=self.digest,
            schedule=self.schedule,eligibility=eligibility,monotonic=monotonic,epoch=epoch)
        self.clear=AttendanceClearBinding(definition,campaign=self.campaign,definition_sha256=self.digest,
            period_at=self.schedule.period_at,dungeon_definition=client_data().dungeon,clock=self.clock)

    def capture(self,s):
        c=s.account.character()
        if (self.schedule.period_at(self.clock()) is None or c is None or c['level']<10):
            self.clear.entries.clear();self.clear.prepared.clear();return
        self.clear.capture(s)

    def prepare_clear(self,s):
        # Only runs captured at the original authenticated loading transition
        # can contribute. Attaching to an ongoing run never backfills clears.
        identity=self.clear.identity(s)
        return self.clear.prepare_clear(s) if identity in self.clear.entries else None

    def finalize(self,s,replies):
        # A group challenge can call LocalSession inside its own SQLite write
        # transaction. Read/project only after commit, via FriendsSession reply
        # or its room periodic branch, without another BEGIN on that writer.
        if getattr(s,'reward_transaction',None) is not None:return replies
        return super().finalize(s,replies)
