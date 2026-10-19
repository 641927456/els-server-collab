"""Typed server-side command joined to the dungeon reward transaction."""
from dataclasses import dataclass

from els_server.domain.attendance_2026 import AttendanceDefinition
from els_server.storage.attendance_2026_progress import AttendanceProgress


@dataclass(frozen=True)
class AttendanceClearCommit:
    definition: AttendanceDefinition
    campaign: str
    definition_sha256: str
    account: int
    character: int
    reward_run_id: str
    period: str
    level: int
    occurred_at: int
    dungeon_id: int
    appropriate_level: bool

    def receipt_identity(self):
        if (not isinstance(self.definition, AttendanceDefinition)
                or self.definition.code != 518
                or type(self.account) is not int or self.account < 1
                or type(self.character) is not int or self.character < 1001):
            raise ValueError('Invalid attendance clear identity')
        return dict(campaign=self.campaign, definition_sha256=self.definition_sha256,
                    account=self.account, character=self.character,
                    reward_run_id=self.reward_run_id, period=self.period,
                    level=self.level, occurred_at=self.occurred_at,
                    dungeon_id=self.dungeon_id, appropriate_level=self.appropriate_level)

    def commit(self, db, owner, reward_run_id, dungeon_clear):
        if not db.in_transaction:
            raise RuntimeError('Attendance must share the reward transaction')
        self.receipt_identity()
        if (owner != self.character or reward_run_id != self.reward_run_id
                or dungeon_clear[0] != self.dungeon_id):
            raise ValueError('Attendance fact does not belong to this clear')
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',
                      (owner,)).fetchone() != (self.account,):
            raise ValueError('Attendance character/account ownership mismatch')
        if db.execute('SELECT definition_sha256 FROM activity518_campaigns WHERE campaign=?',
                      (self.campaign,)).fetchone() != (self.definition_sha256,):
            raise ValueError('Attendance campaign must be initialized and unchanged')
        progress = AttendanceProgress(db,self.definition,campaign_id=self.campaign,
                                      definition_sha256=self.definition_sha256)
        return progress.record_dungeon_atomic(account=str(self.account),
            character=str(self.character), operation='clear:'+reward_run_id,
            period=self.period, level=self.level, occurred_at=self.occurred_at,
            dungeon_id=self.dungeon_id, appropriate_level=self.appropriate_level)
