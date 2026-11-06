"""Current CN secret clears: one atomic account quota/coupon/reward settlement."""
import functools,hashlib,json,sqlite3,struct,time,uuid
from contextlib import closing
from pathlib import Path

@functools.lru_cache(maxsize=1)
def policy():
    from els_server.game_data import CLIENT_SHA,client_data
    directory=Path(__file__).resolve().parents[1]/'data'
    raw=(directory/'secret_clear_rewards.json').read_bytes()
    manifest=json.loads((directory/'secret_clear_rewards.manifest.json').read_bytes());value=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']or value['client_sha256']!=CLIENT_SHA
        or value['policy']!='cn-secret-clear-20261031-v1'or value['weekly_count']!=5
        or value['experience']!=200000000 or len(value['maps'])!=10):raise ValueError('Secret reward exact policy identity')
    data=client_data()
    for row in value['readers']:
        item=data.item(row['template'])
        if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or item['metadata']!=row['metadata']
            or row['group']!=4 or row['max_stack']!=(500 if row['template']==118356 else 1)):
            raise ValueError('Secret reward native inventory reader changed')
    return value,manifest['payload_sha256']

def bind_run(run):
    value,digest=policy();row=value['maps'].get(str(run.identity));run.secret_clear_policy=None
    if row is not None:
        if run.graph['source_sha256']!=row['graph_sha256']:raise ValueError('Secret reward original graph')
        run.secret_clear_policy=(digest,run.identity,run.run_id,run.graph['source_sha256'])

def managed(run):
    if run is None:return False
    value,digest=policy();row=value['maps'].get(str(run.identity))
    if row is None:return False
    if getattr(run,'secret_clear_policy',None)!=(digest,run.identity,run.run_id,run.graph['source_sha256']):raise ValueError('Secret reward run binding changed')
    return True

def _valid(s):
    from els_server.domain.dungeon_hp_c1 import _lease,_solo
    run=s.dungeon_run
    return bool(managed(run)and _lease(s)and _solo(s)and s.role=='game'and s.phase=='dungeon_active'
        and s.dungeon_substage_synced and s.reward_test and s.item_test and not s.clear_notified
        and not s.dungeon_failed and getattr(s,'reward_transaction',None)is None
        and getattr(s,'active_challenge',None)is None and getattr(s,'challenge_deadline',None)is None
        and s.dungeon_participants==frozenset((s.account.uid,))and s.reward_run_id==run.run_id)

def _owner(db,s):
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    from els_server.storage.seal_quests import completed_ids,load_character
    from els_server.domain.region_quests import region_catalog
    require_active_character(db,s.account.uid);require_owner(db,s.account.uid,s.account.account_id)
    role=load_character(db,s.account.uid,s.account.account_id)
    if role['level']!=99 or not region_catalog().dungeon_allowed(s.dungeon_run.identity,role,completed_ids(db,s.account.uid)):
        raise ValueError('Secret reward saved native eligibility')

def _week(now):
    from datetime import datetime,timedelta,timezone
    current=datetime.fromtimestamp(now,timezone(timedelta(hours=8)))
    boundary=(current-timedelta(days=(current.weekday()-2)%7)).replace(hour=10,minute=0,second=0,microsecond=0)
    if current<boundary:boundary-=timedelta(days=7)
    return int(boundary.timestamp())

def _ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS secret_reward_weeks (
        account_id INTEGER NOT NULL,week INTEGER NOT NULL,used INTEGER NOT NULL CHECK(used BETWEEN 0 AND 5),
        PRIMARY KEY(account_id,week))''')
    db.execute('''CREATE TABLE IF NOT EXISTS secret_clear_reward_receipts (
        run_id TEXT PRIMARY KEY,owner INTEGER NOT NULL,account_id INTEGER NOT NULL,
        identity_json TEXT NOT NULL,week INTEGER NOT NULL,eligible INTEGER NOT NULL CHECK(eligible IN(0,1)),
        experience INTEGER NOT NULL CHECK(experience>=0))''')

def _coupon(db,owner):
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_expiration import expired
    from els_server.domain.item_locks import require_unlocked
    candidates=[]
    for item in load_items(db,owner):
        if item['template']not in (118363,118364,118365,118366)or item['group']!=4 or expired(item)or item.get('sealed'):continue
        try:require_unlocked(item)
        except ValueError:continue
        candidates.append(item)
    return min(candidates,key=lambda item:(item.get('expires_at',2**63-1),item['uid']))if candidates else None

def _death_hash(run):
    digest=hashlib.sha256()
    for key,payload in sorted(run.defeated.items()):digest.update(struct.pack('>iI',key,len(payload))+payload)
    return digest.hexdigest()

def settle(s,*,clock=time.time):
    if not managed(getattr(s,'dungeon_run',None)):return None
    if not _valid(s):raise ValueError('Secret clear current session lease/phase')
    run=s.dungeon_run
    if not s.part_end_notified or not run.poll_ready()or run.next.get('kind')!=4:raise ValueError('Secret clear original final condition incomplete')
    value,digest=policy();row=value['maps'][str(run.identity)];elapsed=s.dungeon_clock.seconds()
    context=dict(owner=s.account.uid,account=s.account.account_id,run=run.run_id,dungeon=run.identity,
        stage=run.stage,part=run.part,visits=run.visits,graph=run.graph['source_sha256'],
        policy_sha256=digest,seconds=elapsed,death_sha256=_death_hash(run))
    canonical=json.dumps(context,sort_keys=True,separators=(',',':'));proof=b'cn-secret-clear-v1\0'+canonical.encode()
    def guard():
        if (not _valid(s)or s.dungeon_run is not run or(run.stage,run.part,run.visits)!=(context['stage'],context['part'],context['visits'])
            or _death_hash(run)!=context['death_sha256']or not run.poll_ready()or run.next.get('kind')!=4):raise ValueError('Secret clear source or lease changed before commit')
    from els_server.domain.dungeon_clear import reward_clear_notice,clear_identity_payload
    from els_server.domain.clear_ed_display import amount as result_ed
    from els_server.protocol.local_messages import client_economy_fields
    from els_server.protocol.protocol_codec import Event,encode_event
    from els_server.domain.reward_rules import item_plan
    from els_server.domain.local_artifact_rules import assess_run,clear_base
    from els_server.domain.legacy_pve_exp import experience_limit
    from els_server.storage.inventory_state import load_items
    assessment=assess_run(run,elapsed)
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard();_owner(db,s);_ensure(db)
        prior=db.execute('SELECT owner,account_id,identity_json,week,eligible,experience FROM secret_clear_reward_receipts WHERE run_id=?',(run.run_id,)).fetchone()
        if prior is not None:
            saved=json.loads(prior[2])
            if prior[:2]!=(s.account.uid,s.account.account_id)or saved['context']!=context:raise ValueError('Secret clear conflicting immutable receipt')
            week,eligible,experience=prior[3:];coupon=saved['coupon'];source=saved['source']
        else:
            if db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(run.run_id,)).fetchone():raise ValueError('Historical clear cannot be backfilled')
            week=_week(clock());future=db.execute('SELECT MAX(week)FROM secret_reward_weeks WHERE account_id=?',(s.account.account_id,)).fetchone()[0]
            if future is not None and future>week:raise ValueError('Secret account already has a future reward week')
            used=db.execute('SELECT used FROM secret_reward_weeks WHERE account_id=?AND week=?',(s.account.account_id,week)).fetchone()
            free=used is None or used[0]<value['weekly_count'];coupon=None if free else _coupon(db,s.account.uid)
            eligible=int(free or coupon is not None);source='weekly'if free else'coupon'if coupon is not None else'exhausted'
            experience=value['experience']if eligible else 0
            saved=dict(context=context,coupon=coupon,source=source)
        if prior is None and coupon is not None:
            # Native reward tickets are single instances (metadata0, count1).
            from els_server.storage.item_instances import remove
            if coupon['count']!=1 or coupon['metadata']!=0:raise ValueError('Secret coupon native single-instance identity')
            remove(db,s.account.uid,coupon)
        plan=([item_plan(154065,5),item_plan(154066,100)]if row['stage']<=3 else[item_plan(154065,5),item_plan(118356,1)])if eligible else None
        def encode(balances,best,economy):
            client_economy_fields(balances)
            return reward_clear_notice(result_ed(s,economy['ed'],transaction=db),economy['experience'],s.account.uid,elapsed_seconds=elapsed,best_seconds=best,map_id=run.identity).payload
        attendance=s.activity2026_awards.prepare_clear(s)if getattr(s,'activity2026_awards',None)is not None else None
        receipt=s.account.reward_store.grant(run.run_id,proof,row['ed']if eligible else 0,experience,encode,
            item_plan=plan,dungeon_clear=(run.identity,elapsed),transaction=db,clear_assessment=assessment,
            artifact_base=clear_base(run.identity),title_economy='clear',attendance_clear=attendance,
            experience_limit=experience_limit(),resonance_source='clear')
        if prior is None:
            if source=='weekly':db.execute('INSERT INTO secret_reward_weeks VALUES(?,?,1)ON CONFLICT(account_id,week)DO UPDATE SET used=used+1',(s.account.account_id,week))
            db.execute('INSERT INTO secret_clear_reward_receipts VALUES(?,?,?,?,?,?,?)',(run.run_id,s.account.uid,s.account.account_id,json.dumps(saved,sort_keys=True,separators=(',',':')),week,eligible,experience))
        reply=[];inventory=load_items(db,s.account.uid)
        if coupon is not None:
            from els_server.domain.event_admission import ticket_delta
            current=next((item for item in inventory if(item['group'],item['slot'])==(coupon['group'],coupon['slot'])),None)
            reply.append(ticket_delta(coupon,current))
        if receipt.get('items')and not s.clear_items_synced:
            from els_server.domain.dungeon_drops import pickup_inventory_notice
            identifiers={item['uid']for item in receipt['items']};current=[item for item in inventory if item['uid']in identifiers]
            if current:reply.append(pickup_inventory_notice(current))
        if receipt.get('local_rules'):
            a=receipt['local_rules']['assessment'];reply.append(Event(0x201,kind=0x66b,payload=struct.pack('>ii',a['rank'],a['score'])))
        reply.append(Event(0x201,kind=0xc1,payload=clear_identity_payload(receipt['response'],run.identity)))
        for event in reply:encode_event(event)
        guard()
    s.reward_receipt={'run_id':s.reward_run_id,**receipt};s.clear_items_synced=True;s.clear_notified=True
    return reply
