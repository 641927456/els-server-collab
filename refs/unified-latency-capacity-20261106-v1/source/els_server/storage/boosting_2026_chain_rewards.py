"""Remaining selected678 direct rewards and atomic account ERP milestones.

Minimum cumulative threshold is the existing explicit local join policy,
extended to the original230/250/300/330/350 targets. Existing sufficient bars
are preserved exactly. No SpecialRewardID is added as an extra item, no box
contents are invented, and Pporu eligibility is derived from completed prefix.
"""
import hashlib,json
from els_server.storage.boosting_2026_recovery import RecoverableRewards
from els_server.storage.boosting_2026_participation import integer
from els_server.storage.resonance_2026_profiles import ResonanceProfiles,NEW_PROFILE_POLICY
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.boosting_2026 import SOURCE_SHA256
from els_server.domain.resonance_2026_curve import CURVE_SHA256
from els_server.domain.boosting_2026_chain_items import PROOF_SHA256
from els_server.protocol.protocol_codec import encode_event

POLICY='selected678-local-minimum-cumulative-task-target-v1'
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))

class ChainRewards(RecoverableRewards):
    def __init__(self,db,original,curve,stats):
        super().__init__(db,original)
        self.profiles=ResonanceProfiles(db,curve,stats,new_profile_policy=NEW_PROFILE_POLICY)
        self.policy_sha=hashlib.sha256(canonical([POLICY,SOURCE_SHA256,CURVE_SHA256,hashlib.sha256(stats).hexdigest(),PROOF_SHA256]).encode()).hexdigest()

    def _profile(self,account,character):
        p=self.profiles;p.pages.owner(account,character);p.accounts.migrate_dominated_legacy(account=account,character=character);progress=p.accounts._read(account)
        pages=p.pages.read(account,character);metadata=p._metadata(account,character)
        if progress is None or pages is None or metadata is None or not pages.enabled or metadata[0]>progress.level:
            raise ValueError('Known opened growth resonance profile required')
        return progress,p._state(progress,pages,metadata[1])

    def _grant_direct(self,plan,character):
        # Original169511 awards100 stones. Keep the original receipt quantity
        # while respecting the existing99-per-call API, inside our savepoint.
        from els_server.domain.inventory_items import LOCAL_MAX_STACK
        changed={}
        for entry in plan:
            remaining=entry['quantity']
            while remaining:
                quantity=min(remaining,LOCAL_MAX_STACK)
                for item in grant_items(self.db,[dict(entry,quantity=quantity)],character):
                    changed[item['uid']]=item
                remaining-=quantity
        return list(changed)

    def _effect(self,account,character,task,*,saved=None):
        if task.resonance_target is None:
            if saved is not None:raise ValueError('Unexpected task resonance effect')
            return None,None
        p=self.profiles;current,state=self._profile(account,character);target=task.resonance_target
        operation=f'boost678-task:{account}:{task.quest_id}'
        if saved is not None:
            if type(saved) is not dict or set(saved)!={'policy','target','before','after'} or saved['policy']!=POLICY or saved['target']!=target:
                raise ValueError('Conflicting saved growth resonance policy')
            before,after=saved['before'],saved['after']
            if any(type(v) is not list or len(v)!=3 or any(type(x) is not int for x in v) for v in (before,after)):
                raise ValueError('Invalid saved resonance transition')
            p.accounts._validate_pair(before[1],before[2]);p.accounts._validate_pair(after[1],after[2]);integer(before[0],'original resonance revision')
            expected_level=max(before[1],target);expected_total=before[2] if before[1]>=target else p.accounts.curve.threshold(target)
            changed=before[1]<target
            if after!=[before[0]+int(changed),expected_level,expected_total]:raise ValueError('Invalid original growth floor receipt')
            if current.level<after[1] or current.cumulative_experience<after[2]:
                raise ValueError('Growth receipt has lost committed resonance')
            receipt=self.db.execute('SELECT request_sha256,revision,level,cumulative_experience FROM resonance2026_receipts WHERE account=? AND operation=?',(account,operation)).fetchone()
            if changed:
                if receipt is None:raise ValueError('Missing growth resonance receipt')
                # record checks the exact request and retained receipt audit; an
                # existing operation returns its original result without writes.
                result=p.accounts.record(account=account,character=character,operation=operation,
                    expected_revision=before[0],level=after[1],cumulative_experience=after[2])
                if [result.revision,result.level,result.cumulative_experience]!=after:
                    raise ValueError('Growth resonance operation receipt mismatch')
            else:
                if receipt is not None:raise ValueError('Unexpected operation for sufficient resonance level')
                if current.revision<after[0]:
                    from els_server.storage.boosting_2026_ledger_compat import audited
                    if not audited(self.db,account,'task',task.quest_id):
                        raise ValueError('Unaudited legacy growth receipt')
            encode_event(state.notice())
            return saved,dict(revision=current.revision,level=current.level,total=current.cumulative_experience)
        # Only existing known profiles are credited; missing pages stay unopened.
        # Validate every existing profile before applying an account-wide floor.
        known=[c for c, in self.db.execute('SELECT character FROM resonance2026_characters WHERE account=? ORDER BY character',(account,))]
        for uid in known:
            p.pages.owner(account,uid);pages=p.pages.read(account,uid);metadata=p._metadata(account,uid)
            if metadata is None or metadata[0]>current.level:raise ValueError('Unknown existing growth profile metadata')
            p._state(current,pages,metadata[1])
        before=[current.revision,current.level,current.cumulative_experience]
        if current.level<target:
            current=p.accounts.record(account=account,character=character,operation=operation,expected_revision=current.revision,
                level=target,cumulative_experience=p.accounts.curve.threshold(target))
            for uid in known:p.synchronize(account=account,character=uid)
        current,state=self._profile(account,character);encode_event(state.notice())
        effect=dict(policy=POLICY,target=target,before=before,after=[current.revision,current.level,current.cumulative_experience])
        return effect,dict(revision=current.revision,level=current.level,total=current.cumulative_experience)

    def claim(self,*,account,character,quest,claimed_at,campaign_open,encode):
        if quest in (169500,169501):
            return super().claim(account=account,character=character,quest=quest,claimed_at=claimed_at,campaign_open=campaign_open,encode=encode)
        self._auth(account,character);integer(claimed_at,'reward time',0);task=self.definition.task(quest)
        if campaign_open is not True or not callable(encode):raise ValueError('Qualified campaign and encoder required')
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        plan=[]
        for item in task.items:
            if item.period or item.socket_option or item.item_id not in VERIFIED_TEMPLATES:
                raise ValueError('Original direct reward template unavailable')
            plan.append(dict(template=item.item_id,metadata=VERIFIED_TEMPLATES[item.item_id],quantity=item.quantity,group=TEMPLATE_BAG_GROUPS[item.item_id]))
        if not plan:raise ValueError('Empty direct growth reward')
        with self.participation._savepoint():
            done=self._completed(account,character)
            old=self.db.execute('SELECT claimed_at,receipt FROM boosting2026_task_rewards WHERE account=? AND quest=?',(account,quest)).fetchone();replayed=old is not None
            if replayed:
                receipt=json.loads(old[1]);completed_at=old[0]
                if (receipt.get('schema')!=2 or receipt.get('source')!=SOURCE_SHA256 or receipt.get('account')!=account
                        or receipt.get('character')!=character or receipt.get('quest')!=quest or receipt.get('plan')!=plan
                        or receipt.get('completed_at')!=completed_at or receipt.get('policy_sha256')!=self.policy_sha):
                    raise ValueError('Invalid direct growth reward receipt')
                awarded_ids=receipt.get('awarded_uids')
                if type(awarded_ids) is not list or not awarded_ids or len(set(awarded_ids))!=len(awarded_ids) or any(type(i) is not int or i<=0 for i in awarded_ids):
                    raise ValueError('Invalid awarded growth inventory IDs')
                if task.resonance_target is not None and receipt.get('effect') is None:
                    raise ValueError('Missing committed growth effect')
                effect,resonance=self._effect(account,character,task,saved=receipt.get('effect'))
            else:
                active=self.snapshot(account=account,character=character)
                if active is None or active['id']!=quest or active['count']!=task.required_count:raise ValueError('Growth task is not ready')
                if claimed_at<active['accepted_at']:raise ValueError('Reward precedes task acceptance')
                awarded_ids=self._grant_direct(plan,character);completed_at=claimed_at
                effect,resonance=self._effect(account,character,task)
                receipt=dict(schema=2,source=SOURCE_SHA256,account=account,character=character,quest=quest,completed_at=completed_at,
                    plan=plan,awarded_uids=awarded_ids,effect=effect,policy_sha256=self.policy_sha)
                self.db.execute('INSERT INTO boosting2026_task_rewards VALUES (?,?,?,?,?,?)',(account,character,quest,completed_at,canonical(receipt),SOURCE_SHA256))
                self.db.execute('DELETE FROM boosting2026_active_task WHERE account=?',(account,))
            items=load_items(self.db,character);completed=self._completed(account,character)
            result=dict(quest=quest,completed_at=completed_at,replayed=replayed,items=items,updates=[i for i in items if i['uid'] in awarded_ids],
                active=self.snapshot(account=account,character=character),completed=completed,effect=effect,resonance=resonance,
                pporu_eligible=self.definition.pporu_available(event_active=True,is_bound_character=True,completed=completed))
            response=encode(json.loads(json.dumps(result)))
            if type(response) is not bytes or not 1<=len(response)<=65536:raise ValueError('Growth reward response bound')
            return dict(result,response=response)
