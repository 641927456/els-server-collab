"""Selected campaign task acceptance and type116 Apply progress.

Internal, caller-owned transaction component. Join/reward authorization and
the public packet routes are separate. Completed receipts have no writer here:
only a future verified reward transaction may append them. No task is marked
rewarded merely because its objective becomes ready.
"""
from els_server.domain.boosting_2026 import SOURCE_SHA256
from els_server.storage.boosting_2026_participation import BoostingParticipation,integer


class BoostingTasks:
    def __init__(self,db,original_definition):
        self.db=db
        self.participation=BoostingParticipation(db,original_definition)
        self.definition=self.participation.definition

    def _transaction(self):
        if not self.db.in_transaction:
            raise ValueError('Caller-owned campaign transaction required')

    def initialize(self):
        self._transaction()
        self.db.execute('''CREATE TABLE IF NOT EXISTS boosting2026_active_task(
            account INTEGER PRIMARY KEY,character INTEGER NOT NULL,quest INTEGER NOT NULL,
            accepted_at INTEGER NOT NULL,count INTEGER NOT NULL,
            definition_sha256 TEXT NOT NULL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS boosting2026_task_rewards(
            account INTEGER NOT NULL,character INTEGER NOT NULL,quest INTEGER NOT NULL,
            claimed_at INTEGER NOT NULL,receipt TEXT NOT NULL,
            definition_sha256 TEXT NOT NULL,PRIMARY KEY(account,quest))''')

    def _auth(self,account,character):
        self._transaction()
        level=self.participation._owner_level(account,character)
        bound=self.participation._read(account)
        if bound is None or bound.character_uid!=character or level!=self.definition.minimum_level:
            raise ValueError('Owned level99 campaign participant required')
        return level

    def _completed(self,account,character):
        ids=[]
        for uid,qid,at,receipt,source in self.db.execute('''SELECT character,quest,claimed_at,
                receipt,definition_sha256 FROM boosting2026_task_rewards WHERE account=? ORDER BY quest''',(account,)):
            integer(at,'reward time',0)
            if uid!=character or source!=SOURCE_SHA256 or type(receipt) is not str or not receipt:
                raise ValueError('Invalid committed campaign reward history')
            ids.append(qid)
        self.definition.completed_prefix(ids)
        return tuple(ids)

    def snapshot(self,*,account,character):
        level=self._auth(account,character)
        done=self._completed(account,character)
        next_task=self.definition.next_task(level=level,character_uid=character,
                                          bound_character_uid=character,completed=done)
        row=self.db.execute('''SELECT character,quest,accepted_at,count,definition_sha256
                            FROM boosting2026_active_task WHERE account=?''',(account,)).fetchone()
        if row is None:
            return None
        uid,qid,at,count,source=row
        integer(at,'accepted time',0)
        if (uid!=character or source!=SOURCE_SHA256 or next_task is None or qid!=next_task.quest_id
                or type(count) is not int or not 0<=count<=next_task.required_count):
            raise ValueError('Invalid active campaign task state')
        return dict(id=qid,accepted_at=at,count=count)

    def accept_next(self,*,account,character,quest,accepted_at,campaign_open):
        """Called only after original schedule/location/request admission.

        campaign_open is trusted server policy, never a packet flag. This
        component enforces binding, level and the original reward-order chain.
        """
        self._auth(account,character);integer(accepted_at,'accepted time',0)
        if campaign_open is not True:
            raise ValueError('Campaign schedule not established as open')
        task=self.definition.task(quest)
        with self.participation._savepoint():
            old=self.snapshot(account=account,character=character)
            if old is not None:
                if old['id']!=quest:raise ValueError('Another campaign task is active')
                return old
            done=self._completed(account,character)
            expected=self.definition.next_task(level=99,character_uid=character,
                                               bound_character_uid=character,completed=done)
            if expected is None or expected.quest_id!=task.quest_id:
                raise ValueError('Campaign predecessor has not been rewarded')
            self.db.execute('INSERT INTO boosting2026_active_task VALUES (?,?,?,?,?,?)',
                            (account,character,quest,accepted_at,0,SOURCE_SHA256))
            return dict(id=quest,accepted_at=accepted_at,count=0)

