"""Original solo Mirror lifecycle, owned progression and precommitted replies."""
import hashlib,json,sqlite3,struct,time
from contextlib import closing
from els_server.domain import silver_mirror_policy as policy
from els_server.storage import silver_mirror_state as store
from els_server.protocol.protocol_codec import Event,encode_event

def enabled(s):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    account=getattr(s,'account',None)
    if not bool(account is not None and s.role=='game'and s.client_build=='dx11_260923'and current_lease(s)
        and s.item_test and s.reward_test and account.characters is not None and account.store is not None
        and account.store.uid==account.uid and account.reward_store.uid==account.uid
        and str(account.reward_store.path)==str(account.store.path)):return False
    from els_server.domain.dungeon_rotation import admissions_enabled
    if not admissions_enabled():return False
    try:
        from els_server.domain.equipment_chip_flow import reset_authority
        reset_authority(s)
        return True
    except ValueError:return False

def original(run):
    from els_server.domain.dungeon_routes import route_catalog
    if run is None or run.identity not in policy.ALL:return False
    if run.graph['source_sha256']!=route_catalog().graph(run.identity)['source_sha256']:raise ValueError('Mirror original graph changed')
    return True

def encode(events):
    for event in events:encode_event(event)
    return events

def context(s):
    run=s.dungeon_run
    return(id(s.account),id(s.account.store),id(s.account.root),s.account.uid,s.account.account_id,s.shop_session_id,s.phase,id(run),run.run_id,run.identity,run.stage,run.part,run.visits,
           tuple(sorted(run.defeated.items())),s.reward_run_id,s.dungeon_substage_synced,s.part_end_notified,s.clear_notified)

def authority(s,expected):
    return enabled(s)and context(s)==expected and original(s.dungeon_run)and not getattr(s,'dungeon_failed',False)and not policy.blackout(time.time())and getattr(s.dungeon_run,'silver_mirror_week',None)==policy.week_start(time.time())

def admit(s,run):
    if not original(run):return []
    if not enabled(s)or s.phase!='town_ready'or not s.dungeon_requested or s.requested_dungeon_id!=run.identity:raise ValueError('Mirror native admission authority')
    if getattr(s,'requested_challenge',None)is not None:raise ValueError('Mirror does not alias challenge')
    app=getattr(s,'application',None);world=getattr(app,'world',None)
    party=world.party_of.get(s)if world else None
    if party and(len(party.get('members',()))!=1 or party.get('raid_party')or party.get('challenge')):raise ValueError('Mirror solo source only')
    bound=(s.account.uid,s.account.account_id,s.shop_session_id,s.requested_dungeon_id,s.requested_dungeon_mode,s.phase)
    def allowed():return enabled(s)and not policy.blackout(time.time())and bound==(s.account.uid,s.account.account_id,s.shop_session_id,s.requested_dungeon_id,s.requested_dungeon_mode,s.phase)
    from els_server.protocol.dungeon_messages import dungeon_start
    # Exercise the actual original entry encoder before storing any admission.
    encode([dungeon_start(s.account.get_skills(),s.account.character(),s.account.get_inventory_snapshot()['items'],dungeon_id=run.identity,room_id=10001,account_id=s.account.account_id,bootstrap_port=s.port_probe_port,member_capture=s._capture_luciel_dungeon_hp)])
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');store.guard(db,s.account.uid,s.account.account_id,allowed)
        now=time.time()
        if policy.blackout(now):raise ValueError('Mirror weekly deployment window')
        admitted=store.admit(db,s.account.uid,s.account.account_id,run.run_id,s.shop_session_id,run.identity,run.graph['source_sha256'],allowed,now=now)
        from els_server.domain.dungeon_rotation import in_db
        events=in_db(db,s.account.uid,s.account.account_id)
        offered=store.offers(db,run.run_id)
        if offered:events.append(Event(0x201,kind=0xccb,payload=struct.pack('>I3i',3,*offered)))
        encode(events);store.guard(db,s.account.uid,s.account.account_id,allowed)
    run.silver_mirror_week=admitted['state']['week']
    return events

def boss_proof(run):
    bosses=[n for part in run.parts.values()for n in part['npcs']if n.get('boss')and n.get('active')and not n.get('no_drop')and n.get('team',1)!=0]
    if not bosses or any(n['key']not in run.defeated for n in bosses):raise ValueError('Mirror original Boss has not been defeated')
    return b''.join(struct.pack('>iI',n['key'],len(run.defeated[n['key']]))+run.defeated[n['key']]for n in sorted(bosses,key=lambda n:n['key']))

def world_snapshot(s,db):
    from els_server.domain.elixir_flow import profiles
    from els_server.storage.world_elixirs import _state
    from els_server.protocol.world_buff_messages import snapshot
    rows=_state(db,s.account.uid,int(time.time()))['rows']
    if s.dungeon_run.identity not in policy.STORY.values():rows+=store.world_rows(db,s.account.uid)
    return snapshot(s.account.uid,rows,profiles=profiles(s,db,None))

def choose(s,choice):
    from els_server.domain.dungeon_rotation import body,in_db
    reject=lambda:[Event(0x201,kind=0xccd,payload=struct.pack('>i',-1)+body())]
    run=getattr(s,'dungeon_run',None)
    if not enabled(s)or not original(run)or s.phase!='dungeon_active'or not s.dungeon_substage_synced or s.clear_notified or getattr(s,'dungeon_failed',False):return reject()
    expected=context(s)
    try:
        proof=boss_proof(run)
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
            db.execute('BEGIN IMMEDIATE')
            state=store.select(db,s.account.uid,s.account.account_id,run.run_id,s.shop_session_id,run.identity,run.graph['source_sha256'],choice,proof,lambda:authority(s,expected))
            events=[Event(0x201,kind=0xccd,payload=struct.pack('>i',0)+body(state)),*in_db(db,s.account.uid,s.account.account_id),world_snapshot(s,db)]
            encode(events);store.guard(db,s.account.uid,s.account.account_id,lambda:authority(s,expected))
        return events
    except ValueError:return reject()

def clear_rewards(s,rule):
    run=getattr(s,'dungeon_run',None)
    if not original(run):return None
    if s.clear_notified:return []
    if not enabled(s)or s.phase!='dungeon_active'or not s.dungeon_substage_synced or not s.part_end_notified or not run.next or run.next['kind']!=4:return []
    if s.reward_run_id!=run.run_id or frozenset(getattr(s,'dungeon_participants',()))!=frozenset((s.account.uid,)):return []
    expected=context(s)
    elapsed=s.dungeon_clock.seconds()
    from els_server.domain.local_artifact_rules import assess_run,clear_base
    assessment=assess_run(run,elapsed)
    deaths=hashlib.sha256()
    for key,value in sorted(run.defeated.items()):deaths.update(struct.pack('>iI',key,len(value))+value)
    proof=b'local-static-clear-v2'+struct.pack('>Qiii',s.account.uid,run.identity,run.stage,run.part)+bytes.fromhex(run.graph['source_sha256'])+deaths.digest()
    from els_server.domain.dungeon_clear import reward_clear_notice,clear_identity_payload
    from els_server.protocol.local_messages import client_economy_fields
    def response(balances,best,economy):
        client_economy_fields(balances)
        return reward_clear_notice(economy['ed'],economy['experience'],s.account.uid,elapsed_seconds=elapsed,best_seconds=best,map_id=run.identity).payload
    from els_server.domain.silver_mirror_rewards import rewards,CircuitSource,ClearSource
    from els_server.domain.reward_rules import item_plan
    from els_server.storage.inventory_state import load_items,grant_items
    from els_server.domain.dungeon_drops import pickup_inventory_notice
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE')
        completed=store.complete(db,s.account.uid,s.account.account_id,run.run_id,s.shop_session_id,run.identity,run.graph['source_sha256'],proof,lambda:authority(s,expected))
        selected,circuit=rewards(store.seed(db,run.run_id),completed['result'])
        plan=[item_plan(t,n)for t,n in selected]
        receipt=s.account.reward_store.grant(run.run_id,proof,rule['clear_ed'],rule['clear_experience'],response,item_plan=plan or None,dungeon_clear=(run.identity,elapsed),transaction=db,clear_assessment=assessment,artifact_base=clear_base(run.identity),title_economy='clear',silver_source=ClearSource(db,s.account.uid,run.run_id)if plan else None)
        db.execute('CREATE TABLE IF NOT EXISTS silver_mirror_awards(run_id TEXT PRIMARY KEY,plan_json TEXT NOT NULL,t_items_json TEXT NOT NULL)')
        saved=db.execute('SELECT plan_json,t_items_json FROM silver_mirror_awards WHERE run_id=?',(run.run_id,)).fetchone()
        fingerprint=json.dumps([selected,circuit],sort_keys=True)
        if saved:
            if saved[0]!=fingerprint:raise ValueError('Mirror committed draw changed')
            tc=json.loads(saved[1])
        else:
            tc=grant_items(db,[item_plan(circuit,1)],s.account.uid,silver_source=CircuitSource(db,s.account.uid,run.run_id))if circuit else []
            db.execute('INSERT INTO silver_mirror_awards VALUES (?,?,?)',(run.run_id,fingerprint,json.dumps(tc,sort_keys=True)))
        awarded=[*receipt.get('items',[]),*tc];ids={i['uid']for i in awarded}
        current=[i for i in load_items(db,s.account.uid)if i['uid']in ids]
        events=[pickup_inventory_notice(current)]if current and not s.clear_items_synced else []
        local=receipt.get('local_rules')
        if local:
            a=local['assessment'];events.append(Event(0x201,kind=0x66b,payload=struct.pack('>ii',a['rank'],a['score'])))
        from els_server.domain.dungeon_rotation import in_db
        events+=in_db(db,s.account.uid,s.account.account_id)
        events.append(Event(0x201,kind=0xc1,payload=clear_identity_payload(receipt['response'],run.identity)))
        events.append(world_snapshot(s,db));encode(events)
        store.guard(db,s.account.uid,s.account.account_id,lambda:authority(s,expected))
    s.reward_receipt=dict(run_id=run.run_id,**receipt);s.reward_receipt['items']=awarded
    if awarded:s.clear_items_synced=True
    s.clear_notified=True
    return events

def revival_keys(s):
    """Original solo native selector, only for this exact admitted Mirror run."""
    run=getattr(s,'dungeon_run',None)
    if not enabled(s)or not original(run)or s.phase!='dungeon_active'or not s.dungeon_substage_synced:raise ValueError('Mirror revival actor/source')
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        db.execute('BEGIN');store.guard(db,s.account.uid,s.account.account_id,lambda:enabled(s))
        row=db.execute('SELECT owner,account_id,session_id,dungeon,week,source_sha256,proof_sha256 FROM silver_mirror_runs WHERE run_id=?',(run.run_id,)).fetchone()
        if not row or row!=(s.account.uid,s.account.account_id,s.shop_session_id,run.identity,policy.week_start(time.time()),run.graph['source_sha256'],None):raise ValueError('Mirror revival original admission')
    return ()

def invitation(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219 or not getattr(s.account,'store',None)or type(sequence)is not int or not 1<=sequence<2**32:return None
    from els_server.storage import silver_mirror_invitation as invitations
    from els_server.protocol.career_messages import use_ack
    operation=s.shop_session_id+':mirror-invite-v1:'+str(s.account.uid)+':'+str(sequence)
    if not invitations.candidate(s.account.store.path,s.account.uid,event.payload,operation):return None
    from els_server.storage.local_state import TOWN_SCENES
    def current():
        return(id(s.account),id(s.account.store),id(s.account.root),s.account.uid,s.account.account_id,s.shop_session_id,s.phase,s.active_map,s.dungeon_return_pending)
    bound=current()
    def allowed():
        return enabled(s)and current()==bound and s.phase=='town_ready'and s.active_map in TOWN_SCENES and not s.dungeon_return_pending and {0x28,0x225,0x227}<=s.completed and s.account.get_location()['map']==s.active_map
    if not allowed()or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0:return[use_ack(result=-1)]
    from els_server.domain.dungeon_rotation import in_db
    try:return invitations.use(s.account.store.path,s.account.uid,s.account.account_id,event.payload,operation,allowed,lambda db:in_db(db,s.account.uid,s.account.account_id))
    except ValueError:return[use_ack(result=-1)]

def periodic(s):
    run=getattr(s,'dungeon_run',None)
    if not run or run.identity not in policy.ALL or s.phase!='dungeon_active'or s.clear_notified:return []
    now=time.time()
    if policy.blackout(now)or getattr(run,'silver_mirror_week',None)!=policy.week_start(now):
        from els_server.domain.dungeon_flow import failed
        return failed(s)
    if not enabled(s)or not s.dungeon_substage_synced:return []
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        db.execute('BEGIN');store.guard(db,s.account.uid,s.account.account_id,lambda:enabled(s))
        state=store.read(db,s.account.uid)
        signature=(run.run_id,run.stage,run.part,run.visits,state['week'],state['buff0'],state['buff1'])
        if signature==getattr(s,'_mirror_world_sent',None):return []
        events=encode([world_snapshot(s,db)])
    s._mirror_world_sent=signature
    return events
