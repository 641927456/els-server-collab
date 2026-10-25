"""Recover task counters from server-owned, previously linked clear receipts.

The lost in-memory proof preimage is not invented. Its saved SHA is read from
the authoritative RewardState receipt. The durable admission link establishes
which task generation owned the run before its clear. No history scan creates
new links. Counter and consumed marker always share the caller's transaction.
"""
import hashlib,json,re
from els_server.domain.boosting_2026 import SOURCE_SHA256
from els_server.storage.boosting_2026_first_rewards import FirstRewards,canonical
from els_server.storage.boosting_2026_participation import integer


class RecoverableRewards(FirstRewards):
    def _consume(self,account,character,run_id,expected_digest=None):
        canonical(run_id)
        row=self.db.execute('SELECT account,character,quest,accepted_at,dungeon,consumed_proof,definition_sha256 FROM boosting2026_task_runs WHERE run=?',(run_id,)).fetchone()
        if row is None or row[:2]!=(account,character) or row[6]!=SOURCE_SHA256:
            raise ValueError('Missing authenticated campaign run admission')
        integer(row[2],'run quest',0);integer(row[3],'run accepted time',0);integer(row[4],'run dungeon')
        saved=self.db.execute('SELECT proof_sha256,grant_json FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone()
        if saved is None or type(saved[0]) is not str or re.fullmatch('[0-9a-f]{64}',saved[0]) is None:
            raise ValueError('Invalid committed clear proof digest')
        digest=saved[0]
        if expected_digest is not None and digest!=expected_digest:raise ValueError('Committed clear proof mismatch')
        grant=json.loads(saved[1])
        if type(grant) is not dict:raise ValueError('Invalid committed clear receipt')
        clear=grant.get('dungeon_clear')
        if (type(grant.get('owner',1001)) is not int or grant.get('owner',1001)!=character
                or type(clear) is not list or len(clear)!=2 or any(type(v) is not int for v in clear)
                or clear[0]!=row[4] or not 0<=clear[1]<=2**31-1):
            raise ValueError('Receipt owner or clear dungeon mismatch')
        if row[5] is not None:
            if row[5]!=digest:raise ValueError('Conflicting consumed clear receipt')
            return None
        active=super().snapshot(account=account,character=character);changed=None
        if row[2] and active is not None and (active['id'],active['accepted_at'])==row[2:4]:
            task=self.definition.task(active['id'])
            if task.condition_kind!=8 or row[4] not in task.dungeon_ids:raise ValueError('Run objective mismatch')
            count=min(task.required_count,active['count']+1)
            if count!=active['count']:
                self.db.execute('UPDATE boosting2026_active_task SET count=? WHERE account=?',(count,account))
                changed={**active,'count':count}
        self.db.execute('UPDATE boosting2026_task_runs SET consumed_proof=? WHERE run=?',(digest,run_id))
        return changed

    def observe_clear(self,*,account,character,run_id,proof):
        self._auth(account,character)
        if type(proof) is not bytes or not 1<=len(proof)<=8192:raise ValueError('Run proof bound')
        with self.participation._savepoint():
            return self._consume(account,character,run_id,hashlib.sha256(proof).hexdigest())

    def recover_clears(self,*,account,character):
        """Recover only this active task's linked, committed, unconsumed runs.

        The original objectives require at most five clears. Query only the
        number still needed; unrelated old tasks, pre-acceptance runs, missing
        receipts and another account/character cannot be credited.
        """
        self._auth(account,character)
        with self.participation._savepoint():
            active=super().snapshot(account=account,character=character)
            if active is None:return None
            task=self.definition.task(active['id']);needed=task.required_count-active['count']
            if task.condition_kind!=8 or needed==0:return None
            rows=self.db.execute('''SELECT r.run FROM boosting2026_task_runs r
                JOIN reward_receipts p ON p.run_id=r.run
                WHERE r.account=? AND r.character=? AND r.quest=? AND r.accepted_at=?
                AND r.consumed_proof IS NULL ORDER BY r.rowid LIMIT ?''',
                (account,character,active['id'],active['accepted_at'],needed)).fetchall()
            changed=None
            for (run_id,) in rows:
                result=self._consume(account,character,run_id)
                if result is not None:changed=result
            return changed
