"""Native live actor snapshots for observed spa stays and admitted entry effects."""
from contextlib import closing
from pathlib import Path
import functools,json,sqlite3,struct,time,uuid
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import environment_buffs as store
from els_server.domain.attendance_2026_award_flow import retryable_sqlite_lock

SPA={1500:(0,725)}
FACTORS={202:195,964:1028,965:1029,3082:3254,1087:1188}

@functools.lru_cache(maxsize=1)
def uniforms():
    return {int(k):v for k,v in json.loads((Path(__file__).parents[1]/'data/environment_buffs.json').read_bytes())['uniforms'].items()}

def _binding(s):
    from els_server.domain.assembly_flow import _actor
    return _actor(s)

def _spa(s,db,now):
    from els_server.storage.world_elixirs import _owner
    _owner(db,s.account.uid,s.account.account_id)
    if(s.phase!='town_ready'or s.active_map not in SPA or s.dungeon_return_pending
        or not {0x28,0x225,0x227}<=s.completed or getattr(s,'town_warp_transition',None)is not None):
        raise ValueError('Spa requires current loaded scene')
    saved=db.execute('SELECT town,board FROM location WHERE uid=?',(s.account.uid,)).fetchone()
    location=s.account.get_location()
    from els_server.storage.local_state import TOWN_SCENES
    if saved!=(s.active_map,location['board'])or location['map']!=s.active_map or TOWN_SCENES[s.active_map]!=SPA[s.active_map][1]:
        raise ValueError('Spa scene differs from saved source')
    from els_server.storage.seal_quests import load_character
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_expiration import expired
    from els_server.domain.equipment_requirements import class_matches
    character=load_character(db,s.account.uid,s.account.account_id)
    minimum={13:70,14:70,15:99}.get(character['unit_type'],10)
    if character['level']<minimum:raise ValueError('Spa level requirement')
    divisions=[]
    for item in load_items(db,s.account.uid):
        div=uniforms().get(item['template'])
        if div is None or item['group']!=9 or expired(item,now=now):continue
        from els_server.game_data import client_data
        d=client_data().item(item['template']);raw=d['record']
        slot=36 if raw[8]&4 else 35
        if(item['slot']==slot and d['equip_position']==38 and item['count']==1
            and character['unit_type']==raw[210]and class_matches(character['unit_class'],raw[211])):
            divisions.append(div)
    division=97 if 97 in divisions else 96 if 96 in divisions else 0
    return s.active_map,division

def observe(s):
    if s.phase!='town_ready'or s.active_map not in SPA:
        s._spa_stay=None;return
    try:
        binding=_binding(s)
        with closing(sqlite3.connect(binding[2].path,timeout=0))as db:
            db.execute('BEGIN');facts=_spa(s,db,int(time.time()))
        key=(binding,facts)
        prior=getattr(s,'_spa_stay',None)
        if prior is None or prior['key']!=key:
            s._spa_stay=dict(key=key,start=time.monotonic(),operation='spa-stay:'+str(uuid.uuid4()))
    except ValueError:s._spa_stay=None
    except sqlite3.OperationalError as error:
        if not retryable_sqlite_lock(error):raise
        # Read lock: preserve this observed stay/operation for the next normal tick.

def _grant(s,operation,*,purchase=False):
    binding=_binding(s);now=int(time.time())
    from els_server.domain.elixir_flow import prepare
    from els_server.storage.world_elixirs import _state
    from els_server.storage.npc_trade import balances
    from els_server.protocol.assembly_messages import acknowledgement
    with closing(sqlite3.connect(binding[2].path,timeout=10 if purchase else 0))as db,db:
        db.execute('BEGIN IMMEDIATE');facts=_spa(s,db,now)
        prior=getattr(s,'_spa_stay',None)
        if not purchase:
            needed=180 if facts[1] else 360
            if prior is None or prior['key']!=(binding,facts)or time.monotonic()-prior['start']<needed:
                raise ValueError('Spa continuous observed stay')
        else:
            # Use existing immutable native911 receipt storage for replay/debit.
            from els_server.storage.environment_spa_purchase import debit
            if not debit(db,s.account.uid,operation,facts[0],facts[1]):
                return [acknowledgement(balances(db,s.account.uid)['ed'])]
        source='spa'
        store.put(db,s.account.uid,source,operation,now)
        events=prepare(s)(db,_state(db,s.account.uid,now),None)
        if purchase:events.insert(0,acknowledgement(balances(db,s.account.uid)['ed']))
        for e in events:encode_event(e)
        if _binding(s)!=binding or _spa(s,db,now)!=facts:raise ValueError('Spa source changed before commit')
    return events

def requested(s,event):
    if event.event_id==0x202 and event.kind==0x7d4 and len(event.payload)==8:
        s._environment_entry_mode=struct.unpack_from('>i',event.payload)[0]

def bind(s,previous):
    if s.dungeon_run is not previous:bind_run(s)

def bind_run(s):
    run=s.dungeon_run
    s._environment_entry=(run,1087 if getattr(s,'_environment_entry_mode',1)==2 else 3082)if run is not None else None

def world_rows(s,db,now,*,cold=False):
    result=store.rows(db,s.account.uid,now)
    source=getattr(s,'_environment_entry',None);run=getattr(s,'dungeon_run',None)
    if not cold and source is not None and source[0]is run and s.phase=='dungeon_active'and s.dungeon_substage_synced and not s.dungeon_return_pending:
        from els_server.game_data import client_data
        d=client_data().dungeon(run.identity);conditions=set(d.get('DUNGEON_CHECK_CONDITION',{}).values())
        if 63 in conditions and not conditions.intersection((0,1,2,47,50,65))and d.get('MaxAdequateMemberCount',1)>1:
            result.append(dict(owner=s.account.uid,template=source[1],start=0,end=0,_environment=True))
    return result

def wire_row(owner,row):
    t=row['template'];start,end=row['start'],row['end']
    if row.get('_environment')is not True or row['owner']!=owner or t not in FACTORS:
        raise ValueError('Owned native environment buff')
    if t in(3082,1087):
        if(start,end)!=(0,0):raise ValueError('Entry buff must be run scoped')
    elif not 1<=start<end<2**31 or end-start!=1800:raise ValueError('Environment buff deadline')
    return bytes(8)+struct.pack('>iIQfBif?if?iiiQQ',t,0,owner,0.,1,0,0.,False,FACTORS[t],1.,False,-1,0,0,start,end)

def synchronize(s,events):
    from els_server.domain.elixir_flow import enabled,ready,context,prepare
    if not enabled(s)or not ready(s):return events
    observe(s)
    try:
        with closing(sqlite3.connect(s.account.store.path,timeout=0))as db:
            db.execute('BEGIN');now=int(time.time());rows=world_rows(s,db,now)
            stamp=(context(s),tuple((r['template'],r['start'],r['end'])for r in rows))
            old=getattr(s,'_environment_sent',None)
            if stamp==old or not rows and(old is None or not old[1]):return events
            from els_server.storage.world_elixirs import _state
            notices=prepare(s)(db,_state(db,s.account.uid,now),None)
            for e in notices:encode_event(e)
    except sqlite3.OperationalError as error:
        if not retryable_sqlite_lock(error):raise
        return events
    s._environment_sent=stamp
    return events+notices

def periodic(s,events):
    try:
        observe(s);prior=getattr(s,'_spa_stay',None)
        if prior is not None and time.monotonic()-prior['start']>=(180 if prior['key'][1][1]else 360):
            events+=_grant(s,prior['operation']);s._spa_stay=None;observe(s)
        return synchronize(s,events)
    except sqlite3.OperationalError as error:
        if not retryable_sqlite_lock(error):raise
        # The writer has rolled back/closed. Keep prior committed events and
        # the exact stay/operation; only the next existing tick can grant it.
        return events

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x911 or event.payload not in tuple(struct.pack('>i',t)for t in(0,)):return None
    from els_server.protocol.assembly_messages import acknowledgement
    try:
        if(type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))
            or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
            or s.active_map not in SPA or struct.unpack('>i',event.payload)[0]!=SPA[s.active_map][0]):
            raise ValueError('Spa purchase current envelope/type')
        return _grant(s,s.shop_session_id+':spa-purchase:'+str(s.account.uid)+':'+str(sequence),purchase=True)
    except ValueError:
        return [acknowledgement(s.account.get_reward_balances()['ed'],-1)]
