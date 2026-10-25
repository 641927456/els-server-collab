"""Atomic local678 registration, account resonance floor and configured8173.

The reviewed local rule applies the original target as a minimum cumulative
experience threshold. Already sufficient levels keep their exact progress.
This is explicit local behavior; no claim of recovered retail partial-bar
handling. No character point/page/opaque state is overwritten here: the caller
must encode a verified complete projection before the outer commit succeeds.
"""
import hashlib,json
from els_server.storage.boosting_2026_participation import BoostingParticipation,ParticipationConflict,integer
from els_server.storage.resonance_2026_progress import AccountResonance
from els_server.storage.activity_2026_rewards import RewardDelivery
from els_server.domain.boosting_2026 import SOURCE_SHA256

POLICY='selected678-local-minimum-cumulative-threshold-v1'


class JoinedRewardParticipation(BoostingParticipation):
    def __init__(self,connection,original_definition,curve,catalog):
        super().__init__(connection,original_definition)
        self.resonance=AccountResonance(connection,curve)
        self.delivery=RewardDelivery(connection,catalog)
        self.policy_sha=hashlib.sha256(json.dumps([POLICY,SOURCE_SHA256,catalog.digest],separators=(',',':')).encode()).hexdigest()

    def _transaction(self):
        if not self.db.in_transaction:raise ValueError('Caller-owned complete participation transaction required')

    def initialize(self):
        self._transaction()
        with self._savepoint():
            super().initialize();self.resonance.initialize();self.delivery.initialize()
            self.db.execute('''CREATE TABLE IF NOT EXISTS boosting2026_join_rewards(
                account INTEGER PRIMARY KEY,character INTEGER NOT NULL,operation TEXT NOT NULL,
                joined_at INTEGER NOT NULL,policy_sha256 TEXT NOT NULL,
                resonance_revision INTEGER NOT NULL,resonance_level INTEGER NOT NULL,
                resonance_total INTEGER NOT NULL)''')

    def _read_join(self,account,character):
        row=self.db.execute('SELECT character,operation,joined_at,policy_sha256,resonance_revision,resonance_level,resonance_total FROM boosting2026_join_rewards WHERE account=?',(account,)).fetchone()
        if row is None:return None
        if row[0]!=character or row[3]!=self.policy_sha:raise ParticipationConflict('Account already joined another role or policy')
        binding=self._read(account)
        if binding is None or (binding.character_uid,binding.operation,binding.joined_at)!=(character,row[1],row[2]):
            raise ParticipationConflict('Join receipt has no matching immutable binding')
        self.resonance.migrate_dominated_legacy(account=account,character=character)
        current=self.resonance.snapshot(account=account,character=character)
        self.resonance._validate_pair(row[5],row[6]);integer(row[4],'saved resonance revision')
        if current is None or (current.revision<row[4] and not self._legacy_join(account)) or current.level<row[5] or current.cumulative_experience<row[6]:
            raise ParticipationConflict('Join receipt has no matching committed resonance')
        return row

    def _legacy_join(self,account):
        from els_server.storage.boosting_2026_ledger_compat import audited
        return audited(self.db,account,'join',0)

    def join(self,*,account,character,operation,now,campaign_open,encode):
        self._transaction();integer(now,'observed join time',0)
        if type(campaign_open) is not bool or not callable(encode):raise ValueError('Trusted schedule and complete participation encoder required')
        if type(operation) is not str or not 1<=len(operation)<=120:raise ValueError('Authenticated operation identity required')
        with self._savepoint():
            if self._owner_level(account,character)!=99:raise ValueError('Level99 owned character required')
            previous=self._read_join(account,character);replayed=previous is not None
            if previous is None:
                if not campaign_open:raise ValueError('Campaign is unavailable')
                if self._read(account) is not None:raise ParticipationConflict('Historical binding requires explicit reconciliation')
                current=self.resonance.snapshot(account=account,character=character)
                target=max(self.definition.join_resonance_target,current.level if current else 1)
                # Keep exact existing cumulative EXP when already sufficient.
                # A lower level reaches the original target's minimal total.
                if current is None or current.level<target:
                    current=self.resonance.record(account=account,character=character,
                        operation='boost678-join:'+operation,expected_revision=current.revision if current else 0,
                        level=target,cumulative_experience=self.resonance.curve.threshold(target))
                bound=self.record_binding(account=account,character=character,operation=operation,joined_at=now)
                self.db.execute('INSERT INTO boosting2026_join_rewards VALUES (?,?,?,?,?,?,?,?)',
                    (account,character,operation,bound.joined_at,self.policy_sha,current.revision,current.level,current.cumulative_experience))
            else:
                current=self.resonance.snapshot(account=account,character=character)
                bound=self._read(account)
            # The provider verifies binding again and either grants once or
            # reads the original permanent item receipt, including a used box.
            def encode_delivery(award):
                return encode(dict(award,binding=bound,resonance=current,join_replayed=replayed,policy=POLICY))
            result=self.delivery.participation(account=account,character=character,now=now,qualified=True,encode=encode_delivery)
            return dict(result,binding=bound,resonance=current,join_replayed=replayed,policy=POLICY)
