"""Ordinary fatigue on existing admission, loaded barriers and owned196 use.

New runs carry a source seal. Old unmarked runs are never charged. Group
barriers prepare all native notifications/mailboxes in one SQLite writer.
"""
from contextlib import closing
from pathlib import Path
import hashlib,json,math,sqlite3,struct,uuid
from els_server.domain import normal_fatigue_rules as rules
from els_server.storage import normal_fatigue as storage
from els_server.protocol.protocol_codec import Event,encode_event

def _binding(s,phases):
    from els_server.domain.equipment_chip_flow import reset_authority
    reset_authority(s)
    a=s.account;path=Path(a.store.path).resolve();app=getattr(s,'application',None)or getattr(s,'_chip_reset_local_application',None)
    if s.client_build!='dx11_260923'or s.role!='game'or s.phase not in phases or not s.item_test or s.account.reward_store.uid!=a.uid or Path(a.reward_store.path).resolve()!=path or getattr(s,'reward_transaction',None)is not None or getattr(s,'coop_error',False)or getattr(s,'social_overflow',False):raise ValueError('Ordinary fatigue current application actor')
    return(s,a,a.root,a.store,a.reward_store,a.characters,app,getattr(s,'identity',None),s.shop_session_id,a.uid,a.account_id,path,s.phase)

def _guard(s,bound,phases):
    def prepare(db):
        if _binding(s,phases)!=bound:raise ValueError('Ordinary fatigue actor changed in writer')
        storage._writer(db,bound[11]);storage._actor(db,bound[9],bound[10])
    return prepare

def admission(s,mid):
    if not rules.enabled():return True
    r=rules.route(mid)
    if r is None or r['cost']==0:return True
    try:
        b=_binding(s,('town_ready',));path=b[11]
        with closing(sqlite3.connect(path,timeout=10))as db:
            db.execute('BEGIN');state=storage.snapshot(db,b[9],b[10])
            if _binding(s,('town_ready',))!=b:raise ValueError('Ordinary fatigue admission actor changed')
            return state['current']>0
    except(ValueError,sqlite3.Error):return False

def bind(s,*,epoch=None):
    """Called only by original successful run admission, never by load retry."""
    s._normal_fatigue_origin=None
    s._random_mission_origin=None
    if not rules.enabled():return
    run=s.dungeon_run;mid=run.identity if run is not None else s.dungeon_id
    r=rules.route(mid,run)
    if r is None or r['cost']==0:return
    epoch=run.run_id if run is not None else(epoch or s.reward_run_id)
    if epoch is None:return
    uuid.UUID(epoch)
    s._normal_fatigue_origin=(run,epoch,s.reward_run_id,mid,r['graph_sha256'],rules.policy()['sha256'])
    from els_server.domain.random_mission_flow import bind as mission_bind
    mission_bind(s)

def _stage(s,part=None):
    run=s.dungeon_run;origin=getattr(s,'_normal_fatigue_origin',None)
    if origin is None:return None
    mid=run.identity if run is not None else s.dungeon_id;r=rules.route(mid,run)
    epoch=run.run_id if run is not None else origin[1]
    if origin!=(run,epoch,s.reward_run_id,mid,r['graph_sha256'],rules.policy()['sha256']):raise ValueError('Ordinary fatigue original run seal changed')
    stage,subpart,visits=(run.stage,run.part,run.visits)if run is not None else(s.gate_stage,0,s.gate_stage)
    if part is not None:subpart=part
    context=dict(epoch=epoch,reward_run=s.reward_run_id,owner=s.account.uid,dungeon=mid,stage=stage,part=subpart,visits=visits,graph_sha256=r['graph_sha256'])
    return r,context

def _envelope(event):
    if event.event_id!=0x202 or event.performers not in((),(0,))or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0:raise ValueError('Ordinary fatigue original load envelope')

def _loading_plan(s,event):
    """Validate and preencode the original pure loaded/part response."""
    _envelope(event);run=s.dungeon_run;part=None
    if event.kind==0xb3:
        if len(event.payload)!=9 or event.payload[:5]!=bytes(5)or not math.isfinite(v:=struct.unpack_from('>f',event.payload,5)[0])or not 0<=v<=1e9 or s.dungeon_substage_synced:return None
        events=[Event(0x201,kind=0xb4,payload=bytes(4)),Event(0x201,kind=0xb5,payload=struct.pack('>iQ',0,s.account.uid)),Event(0x201,kind=0xb6,payload=bytes(16))]
    elif event.kind==0xbb:
        if run is None or event.payload!=struct.pack('>b',run.part)or not s.part_end_notified or s.gate_stage_loading or s.clear_notified or not run.poll_ready()or run.next['kind']!=0:return None
        from els_server.domain.story_controller_retirements import gate_predecessor_blocked
        if gate_predecessor_blocked(run):return None
        part=run.next['part']
        if run.next['stage']!=run.stage:raise ValueError('Ordinary fatigue cross-stage subpart')
        events=[Event(0x201,kind=0xbc,payload=bytes(4))]
    else:return None
    stage=_stage(s,part)
    if stage is None:return None
    from els_server.protocol.dungeon_messages import initial_part,begin_substage
    if run is None:
        from els_server.domain.dungeon_population import population
        entries=tuple((n['key'],n['template'])for n in population(s.gate_stage,hp_context=getattr(s,'_c1_hp_context',None))['npcs'])if s.population_test else()
        current_part=0
    else:
        current_part=run.part if part is None else part
        entries=tuple((n['key'],n['template'])for n in run.parts[current_part]['npcs'])
    events.extend([initial_part(current_part),begin_substage(current_part,npc_entries=entries)])
    for e in events:encode_event(e)
    return stage,events

def _room_binding(members,room,event):
    bindings=tuple(_binding(s,('dungeon_active',))for s in members);paths={b[11]for b in bindings};owners=frozenset(b[9]for b in bindings)
    if len(paths)!=1 or len(owners)!=len(members):raise ValueError('Ordinary fatigue barrier roster/save')
    app=bindings[0][6];dispatcher=app.world.dungeons
    if any(b[6]is not app for b in bindings):raise ValueError('Ordinary fatigue shared application')
    if room is None:
        if len(members)!=1 or dispatcher.room(members[0])is not None:raise ValueError('Ordinary fatigue solo room')
        generation=None
    else:
        expected='substage'if event.kind==0xb3 else'part_end'
        if room.phase!=expected or tuple(room.members)!=members or tuple(room.party['members'])!=members or room.party.get('run')is not room or len(members)<2 or len(members)>4:raise ValueError('Ordinary fatigue original shared barrier')
        if any(dispatcher.room(s)is not room or app.world.party_of.get(s)is not room.party for s in members):raise ValueError('Ordinary fatigue shared membership changed')
        if members[0].dungeon_run is not None:
            from els_server.domain.friends_spawns import _members,_static_origin
            generation=_members(dispatcher,room)
            if getattr(room,'static_actor_origin',None)!=_static_origin(room)or getattr(room,'static_actor_generation',None)!=generation:raise ValueError('Ordinary fatigue static origin/generation changed')
        else:generation=(room,room.seed,room.identity)
    identities=[]
    for s in members:
        if s.dungeon_participants!=owners or s.clear_notified or s.dungeon_failed:raise ValueError('Ordinary fatigue loaded participation')
        run=s.dungeon_run
        if run is None:epoch=room.seed if room else s.reward_run_id
        else:epoch=run.run_id
        expected=str(uuid.uuid5(uuid.UUID(epoch),'reward:'+str(s.account.uid)))if room else epoch
        if s.reward_run_id!=expected or room is not None and(epoch, s.dungeon_id)!=(room.seed,room.identity):raise ValueError('Ordinary fatigue original reward epoch')
        identities.append((run,epoch,s.reward_run_id,s.gate_stage,s.dungeon_substage_synced,s.gate_stage_loading,s.part_end_notified,None if run is None else(run.stage,run.part,run.visits,json.dumps(run.next,sort_keys=True)),id(getattr(s,'mailbox',None))))
    return(bindings,generation,tuple(identities),next(iter(paths)))

def charge(members,event,*,room=None):
    """One all-roster writer before any original stage is adopted."""
    if not rules.enabled():return{}
    members=tuple(members)
    plans={s:_loading_plan(s,event)for s in members}
    if not any(plans.values()):return{}
    if not all(plans.values()):raise ValueError('Ordinary fatigue partial group origin')
    contexts=[p[0][1]for p in plans.values()]
    if len({(c['epoch'],c['dungeon'],c['stage'],c['part'],c['visits'],c['graph_sha256'])for c in contexts})!=1:raise ValueError('Ordinary fatigue stage mismatch')
    bound=_room_binding(members,room,event);path=bound[3]
    def prepare(db):
        if _room_binding(members,room,event)!=bound:raise ValueError('Ordinary fatigue stage generation changed')
        storage._writer(db,path)
        for s in members:
            storage._actor(db,s.account.uid,s.account.account_id)
            if _loading_plan(s,event)!=plans[s]:raise ValueError('Ordinary fatigue native plan changed')
    notices={}
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');prepare(db)
        for s in members:
            r,c=plans[s][0];debit_context,amount=rules.debit(r,c)
            operation='fatigue-stage:'+hashlib.sha256(json.dumps(debit_context,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            applied=storage._apply(db,path,s.account.uid,s.account.account_id,operation,'stage',debit_context,rules.policy()['sha256'],amount,prepare=prepare)
            notices[s]=[applied['notification']]
        from els_server.domain.random_mission_flow import in_loading_writer as mission_stage
        for actor,extra in mission_stage(db,path,members,event,room,prepare).items():notices[actor]+=extra
        # Encode actual original responses and all recipient mailboxes while
        # either a source/actor/encoding failure can still roll back everyone.
        if room is not None:
            from els_server.domain.party_commands import _prepared_boxes
            _prepared_boxes([(s,plans[s][1]+notices[s])for s in members],[])
        prepare(db)
    return notices

_PERMIT_SEAL=object()
class _LoadedPermit:
    __slots__=('seal','owner','kind','payload','origin','plan')
    def __init__(self,s,event):
        self.seal=_PERMIT_SEAL;self.owner=s;self.kind=event.kind;self.payload=bytes(event.payload);self.origin=s._normal_fatigue_origin;self.plan=_loading_plan(s,event)

def shared_loaded(members,event,original,*,room):
    """Charge all members before invoking original per-member loaded handlers."""
    members=tuple(members);notices=charge(members,event,room=room)
    permits={s:_LoadedPermit(s,event)for s in notices}
    try:
        for s,p in permits.items():
            if getattr(s,'_normal_fatigue_group_prepared',None)is not None:raise ValueError('Nested fatigue loaded barrier')
            s._normal_fatigue_group_prepared=p
        return[(s,original(s)+notices.get(s,[]))for s in members]
    finally:
        for s,p in permits.items():
            if getattr(s,'_normal_fatigue_group_prepared',None)is p:del s._normal_fatigue_group_prepared

def loaded(s,event):
    if not rules.enabled()or getattr(s,'_normal_fatigue_origin',None)is None:return[]
    permit=getattr(s,'_normal_fatigue_group_prepared',None)
    if permit is not None:
        if type(permit)is not _LoadedPermit or permit.seal is not _PERMIT_SEAL or permit.owner is not s or(permit.kind,permit.payload,permit.origin,permit.plan)!=(event.kind,event.payload,s._normal_fatigue_origin,_loading_plan(s,event)):raise ValueError('Original fatigue group permit changed')
        return[]
    return charge((s,),event).get(s,[])

def synchronization(s,events):
    if not rules.enabled()or s.phase not in('town_ready','dungeon_active')or getattr(s,'reward_transaction',None)is not None:return events
    import time
    clock=storage._clock();today=storage._day(clock);tick=time.monotonic()
    # Ordinary movement/combat relay traffic never opens a writer. Check once
    # per second, or immediately after an original persistent-effect response.
    changed=any(e.kind in(0x197,0x241,0xf5,0x21a,0xaf,0xc1,0xd9,0x2a)for e in events)
    last=getattr(s,'_normal_fatigue_last_check',None)
    key=(s.shop_session_id,s.account.uid,today)
    if not changed and last is not None and last[:3]==key and tick<last[3]:return events
    try:
        b=_binding(s,('town_ready','dungeon_active'));prepare=_guard(s,b,('town_ready','dungeon_active'));path=b[11]
        with closing(sqlite3.connect(path,timeout=10))as db:
            db.execute('BEGIN');prepare(db);saved=storage._saved(db,b[9]);state=storage.snapshot(db,b[9],b[10],now=clock);prepare(db)
        if saved is None or today>saved['day']:
            with closing(sqlite3.connect(path,timeout=10))as db,db:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');prepare(db)
                # Re-read only after acquiring the real writer; an intervening
                # same-day level/potion operation must never be overwritten.
                saved=storage._saved(db,b[9])
                if saved is None or today>saved['day']:
                    r=storage._apply(db,path,b[9],b[10],'fatigue-reset:'+str(b[9])+':'+str(today),'reset',dict(owner=b[9],day=today),rules.policy()['sha256'],4800,prepare=prepare,now=clock);state=r['state']
                else:state=storage.snapshot(db,b[9],b[10],now=clock)
                notice=storage.notification(state['current'])
                for event in(*events,notice):encode_event(event)
                prepare(db)
        current=state['current'];notice=storage.notification(current);encode_event(notice)
        # A successful197 assigns absolute fatigue even when an unrelated
        # cube leaves its reserved field0. Follow the final wire assignment;
        # the cached visible value predates these replies and cannot mask it.
        assigned=None
        for event in events:
            if event.kind==0x241 and len(event.payload)==4:
                assigned=struct.unpack('>i',event.payload)[0]
            elif event.kind==0x197 and len(event.payload)>=12 and event.payload[:4]==bytes(4):
                assigned=struct.unpack_from('>i',event.payload,8)[0]
        if (assigned is not None and assigned!=current or
            assigned is None and getattr(s,'_normal_fatigue_visible',None)!=current):events=[*events,notice]
        s._normal_fatigue_visible=current;s._normal_fatigue_last_check=(*key,tick+1.)
        return events
    except(ValueError,sqlite3.Error):return events

def potion(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x196:return None
    a=getattr(s,'account',None);store=getattr(a,'store',None)
    if store is None:return None
    from els_server.storage.normal_fatigue_potions import recognizes,perform,result
    operation=s.shop_session_id+':ordinary-fatigue-potion:'+str(a.uid)+':'+str(sequence)
    if not recognizes(store.path,a.uid,event.payload,operation):return None
    try:
        _envelope(event);b=_binding(s,('town_ready',))
        if type(sequence)is not int or not 0<sequence<2**32 or not {0x28,0x225,0x227}<=s.completed:raise ValueError('Ordinary-fatigue original town item request')
        prepare=_guard(s,b,('town_ready',));return perform(b[11],b[9],b[10],event.payload,operation,prepare=prepare)
    except ValueError:
        return result(0,0,code=-1)
