"""Internal first-two-task clear/award transactions; no public packet route.

The caller owns BEGIN IMMEDIATE and must commit before sending any response.
Run admission and proof bytes come from the authenticated dungeon lifecycle,
never client task claims. A pre-existing reward receipt cannot be registered
as a new run. Binding/join8173, campaign clocks and full F5 are separate work.
"""
import hashlib,json,uuid
from els_server.domain.boosting_2026 import SOURCE_SHA256
from els_server.storage.boosting_2026_tasks import BoostingTasks
from els_server.storage.boosting_2026_participation import integer
from els_server.storage.inventory_state import grant_items,load_items


def canonical(value):
    if type(value) is not str or str(uuid.UUID(value))!=value:
        raise ValueError('Server run UUID required')
    return value


class FirstRewards(BoostingTasks):
    def initialize(self):
        super().initialize()
        self.db.execute('''CREATE TABLE IF NOT EXISTS boosting2026_task_runs(
            run TEXT PRIMARY KEY,account INTEGER NOT NULL,character INTEGER NOT NULL,
            quest INTEGER NOT NULL,accepted_at INTEGER NOT NULL,dungeon INTEGER NOT NULL,
            consumed_proof TEXT,definition_sha256 TEXT NOT NULL)''')

    def admit_run(self,*,account,character,run_id,dungeon):
        """Call once at real server run admission, never retrospective recovery.

        A nonmatching or not-yet-accepted quest is not eligible for this run.
        Reconnection recovery only reuses an already persisted run linkage.
        """
        self._auth(account,character);canonical(run_id);integer(dungeon,'dungeon')
        with self.participation._savepoint():
            old=self.db.execute('SELECT account,character,quest,accepted_at,dungeon,consumed_proof,definition_sha256 FROM boosting2026_task_runs WHERE run=?',(run_id,)).fetchone()
            if old is not None:
                if (old[0],old[1],old[4],old[6])!=(account,character,dungeon,SOURCE_SHA256):
                    raise ValueError('Conflicting campaign run binding')
                return old[2]
            if self.db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone():
                raise ValueError('Cannot register an already rewarded run')
            active=self.snapshot(account=account,character=character)
            task=self.definition.task(active['id']) if active else None
            # Zero is a persistent ineligible-run marker. A run admitted before
            # acceptance cannot later be attached to a newly accepted quest.
            eligible=task is not None and task.condition_kind==8 and dungeon in task.dungeon_ids
            qid=task.quest_id if eligible else 0;at=active['accepted_at'] if eligible else 0
            self.db.execute('INSERT INTO boosting2026_task_runs VALUES (?,?,?,?,?,?,NULL,?)',
                            (run_id,account,character,qid,at,dungeon,SOURCE_SHA256))
            return qid

    def observe_clear(self,*,account,character,run_id,proof):
        """Consume a committed clear receipt, once, using its original proof.

        Count and consumed marker share this transaction. No best-time row or
        receipt without a clear effect can advance the objective. If the base
        clear committed but this call failed, retry the persisted run linkage.
        """
        self._auth(account,character);canonical(run_id)
        if type(proof) is not bytes or not 1<=len(proof)<=8192:raise ValueError('Run proof bound')
        digest=hashlib.sha256(proof).hexdigest()
        return self._consume_receipt(account=account,character=character,run_id=run_id,digest=digest)

    def _consume_receipt(self,*,account,character,run_id,digest):
        self._auth(account,character);canonical(run_id)
        if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Committed reward proof digest required')
        with self.participation._savepoint():
            row=self.db.execute('SELECT account,character,quest,accepted_at,dungeon,consumed_proof,definition_sha256 FROM boosting2026_task_runs WHERE run=?',(run_id,)).fetchone()
            if row is None or row[:2]!=(account,character) or row[6]!=SOURCE_SHA256:
                raise ValueError('Missing authenticated campaign run admission')
            saved=self.db.execute('SELECT proof_sha256,grant_json FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone()
            if saved is None or saved[0]!=digest:raise ValueError('Committed clear proof required')
            grant=json.loads(saved[1]);clear=grant.get('dungeon_clear')
            if (type(grant.get('owner',1001)) is not int or grant.get('owner',1001)!=character
                    or type(clear) is not list or len(clear)!=2
                    or any(type(v) is not int for v in clear) or clear[0]!=row[4] or not 0<=clear[1]<=2**31-1):
                raise ValueError('Receipt owner or clear dungeon mismatch')
            if row[5] is not None:
                if row[5]!=digest:raise ValueError('Conflicting campaign clear replay')
                return None
            active=self.snapshot(account=account,character=character);changed=None
            if row[2] and active is not None and (active['id'],active['accepted_at'])==row[2:4]:
                task=self.definition.task(active['id'])
                if task.condition_kind!=8 or row[4] not in task.dungeon_ids:raise ValueError('Run objective mismatch')
                count=min(task.required_count,active['count']+1)
                if count!=active['count']:
                    self.db.execute('UPDATE boosting2026_active_task SET count=? WHERE account=?',(count,account))
                    changed={**active,'count':count}
            self.db.execute('UPDATE boosting2026_task_runs SET consumed_proof=? WHERE run=?',(digest,run_id))
            return changed

    def recover_committed(self,*,account,character,limit=64):
        """Consume already-admitted committed clear receipts after cold reconnect.

        No run is created, no client-supplied proof or counter is accepted, and
        no item/reward balance is reissued. UUID, owner, map, definition and task
        generation checks are the same as the live receipt path. The legacy
        owner-omitted encoding denotes1001, matching current RewardState.
        """
        self._auth(account,character)
        if type(limit) is not int or not 1<=limit<=256:raise ValueError('Recovery batch limit')
        changed=[]
        with self.participation._savepoint():
            rows=self.db.execute("""SELECT r.run,p.proof_sha256 FROM boosting2026_task_runs r
                JOIN reward_receipts p ON p.run_id=r.run
                WHERE r.account=? AND r.character=? AND r.consumed_proof IS NULL
                ORDER BY r.accepted_at,r.run LIMIT ?""",(account,character,limit)).fetchall()
            for run,digest in rows:
                row=self._consume_receipt(account=account,character=character,run_id=run,digest=digest)
                if row is not None:changed.append(row)
        return changed

    def claim(self,*,account,character,quest,claimed_at,campaign_open,encode):
        """Grant only169500/169501 original direct items and unlock the chain.

        encode must serialize current authoritative inventory/state inside this
        transaction. Replays recompute a current snapshot; stored old inventory
        deltas are never blindly resent. A completed quest cannot grant twice.
        """
        self._auth(account,character);integer(claimed_at,'reward time',0)
        task=self.definition.task(quest)
        if quest not in (169500,169501) or task.resonance_target is not None or task.opens_pporu:
            raise ValueError('Only verified first-two direct rewards supported')
        if campaign_open is not True or not callable(encode):raise ValueError('Qualified claim policy and encoder required')
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        plan=[]
        for item in task.items:
            if item.period or item.socket_option or item.item_id not in VERIFIED_TEMPLATES:
                raise ValueError('Original reward inventory definition unavailable')
            plan.append(dict(template=item.item_id,metadata=VERIFIED_TEMPLATES[item.item_id],quantity=item.quantity,group=TEMPLATE_BAG_GROUPS[item.item_id]))
        with self.participation._savepoint():
            done=self._completed(account,character)
            old=self.db.execute('SELECT claimed_at,receipt FROM boosting2026_task_rewards WHERE account=? AND quest=?',(account,quest)).fetchone()
            replayed=old is not None
            if replayed:
                receipt=json.loads(old[1]);completed_at=old[0]
                if (receipt.get('schema')!=1 or receipt.get('source')!=SOURCE_SHA256
                        or receipt.get('account')!=account or receipt.get('character')!=character
                        or receipt.get('quest')!=quest or receipt.get('plan')!=plan
                        or receipt.get('completed_at')!=completed_at):
                    raise ValueError('Invalid original campaign reward receipt')
                awarded_ids=receipt['awarded_uids']
                if (type(awarded_ids) is not list or not awarded_ids or len(set(awarded_ids))!=len(awarded_ids)
                        or any(type(v) is not int or v<=0 for v in awarded_ids)):
                    raise ValueError('Invalid reward inventory identities')
            else:
                active=self.snapshot(account=account,character=character)
                if active is None or active['id']!=quest or active['count']!=task.required_count:
                    raise ValueError('Campaign task is not ready')
                if claimed_at<active['accepted_at']:raise ValueError('Reward precedes task acceptance')
                awarded=grant_items(self.db,plan,character);awarded_ids=[i['uid'] for i in awarded]
                completed_at=claimed_at
                receipt=dict(schema=1,source=SOURCE_SHA256,account=account,character=character,quest=quest,completed_at=completed_at,plan=plan,awarded_uids=awarded_ids)
                self.db.execute('INSERT INTO boosting2026_task_rewards VALUES (?,?,?,?,?,?)',(account,character,quest,completed_at,json.dumps(receipt,sort_keys=True,separators=(',',':')),SOURCE_SHA256))
                self.db.execute('DELETE FROM boosting2026_active_task WHERE account=?',(account,))
            items=load_items(self.db,character)
            result=dict(quest=quest,completed_at=completed_at,replayed=replayed,items=items,
                        updates=[i for i in items if i['uid'] in awarded_ids],
                        active=self.snapshot(account=account,character=character),
                        completed=self._completed(account,character))
            # Deep copy: an encoder cannot alter the stored result containers.
            response=encode(json.loads(json.dumps(result)))
            if type(response) is not bytes or not 1<=len(response)<=65536:raise ValueError('Campaign reward response bound')
            return {**result,'response':response}
