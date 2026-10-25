"""Prepare immutable clear facts before the existing reward transaction.

Explicit injection only. The production event schedule and session bootstrap are
still pending; this class does not invent a reset hour or enable any rewards.
"""
from els_server.domain.seal_quests import appropriate_level_range
from els_server.storage.attendance_2026_commit import AttendanceClearCommit


class AttendanceClearBinding:
    def __init__(self, definition, *, campaign, definition_sha256,
                 period_at, dungeon_definition, clock):
        self.definition = definition
        self.campaign = campaign
        self.digest = definition_sha256
        self.period_at = period_at
        self.dungeon_definition = dungeon_definition
        self.clock = clock
        self.entries = {}
        self.prepared = {}

    @staticmethod
    def identity(session, *, loading=False):
        if (session.role != 'game' or session.phase not in (('dungeon_loading','dungeon_active') if loading else ('dungeon_active',))
                or session.client_build != 'dx11_260923' or not session.reward_test
                or session.account.characters is None or not session.reward_run_id
                or getattr(session,'released',False)):
            raise ValueError('Attendance requires an owned active dungeon session')
        run = session.dungeon_run
        if run is None and session.dungeon_id != 30000:
            raise ValueError('Missing source dungeon run')
        return (session.account.account_id,session.account.uid,
                run.run_id if run is not None else session.reward_run_id,
                session.reward_run_id,run.identity if run is not None else 30000)

    def capture(self, session):
        identity = self.identity(session, loading=True)
        if session.clear_notified:
            raise ValueError('Cannot capture a level after clear')
        if identity not in self.entries:
            character = session.account.character()
            if character is None or character['uid'] != session.account.uid:
                raise ValueError('Owned character required')
            self.entries = {identity: character['level']}
            self.prepared.clear()

    def prepare_clear(self, session):
        identity = self.identity(session)
        if getattr(session,'dungeon_failed',False) or identity not in self.entries:
            raise ValueError('Missing eligible entry-level evidence')
        if identity not in self.prepared:
            now = self.clock()
            if type(now) is not int or now < 0:
                raise ValueError('Server epoch seconds required')
            period = self.period_at(now)
            if period is None:
                self.prepared[identity] = None
            else:
                account, character, run, reward, dungeon = identity
                level = self.entries[identity]
                low, high = appropriate_level_range(self.dungeon_definition(dungeon))
                self.prepared[identity] = AttendanceClearCommit(self.definition,
                    self.campaign,self.digest,account,character,reward,period,
                    level,now,dungeon,low <= level <= high)
        return self.prepared[identity]
