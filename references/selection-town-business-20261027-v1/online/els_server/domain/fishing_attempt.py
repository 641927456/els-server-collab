"""Finite original1500 start/stop and authoritative35s local settlement.

UI, rod animation and result effects remain the native8B5/7/8 consumers.
The server schedules economic authority only, never replays offline catches.
"""
import sqlite3,time
from contextlib import closing
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol import fishing_messages as wire
from els_server.storage import fishing_attempt as storage


def _selection_binding(s):
    from els_server.domain.fishing_equipment import _reply_binding
    objects,facts=_reply_binding(s)
    # During original28 selection the world has not attached a town entry;
    # FriendsWorld.room returns a new empty default on each read. Bind the
    # concrete world and its absence of membership instead of that temporary.
    world=objects[6]
    if world is not None and s not in world.members:
        objects=(*objects[:7],None,None)
    from pathlib import Path
    paths=(str(Path(s.account.store.path).resolve()),str(Path(s.account.characters.path).resolve()))
    app=getattr(s,'application',None)
    if app is not None:paths+= (str(Path(app.config.state_file).resolve()),)
    if len(set(paths))!=1:raise ValueError('Fishing original same database paths')
    return objects,facts+(paths,)


def _same(s,bound):
    try:
        from els_server.domain.dungeon_equipment_loot_flow import current_lease
        now=_selection_binding(s)
        return bool(current_lease(s)and all(a is b for a,b in zip(now[0],bound[0]))and now[1]==bound[1])
    except(ValueError,AttributeError,KeyError,TypeError):return False


def initialize_login(s,answer):
    if not(s.item_test and s.client_build=='dx11_260923'and s.role=='game'and s.account.characters is not None):return answer
    if s.phase not in('characters_ready','channels_ready'):raise ValueError('Life original fresh selection only')
    if not storage.WRITER_ENABLED:return answer
    bound=_selection_binding(s);owner=s.account.uid;account=s.account.account_id
    from els_server.storage import life_stamina as life
    from els_server.protocol.local_messages import player_initialization
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            if not _same(s,bound):raise ValueError('Life original selected actor')
            state=life.initialize(db,owner,account,s.shop_session_id,time.time())
            saved=s.account.get_inventory_snapshot();character=dict(s.account.character(),life_stamina=state)
            reply=list(answer)
            if not reply or reply[0].kind!=0x2a:raise ValueError('Life original first initialization')
            reply[0]=player_initialization(s.account.get_location(),initialize_attributes=s.enter_dungeon,
                economy=saved['balances'],items=saved['items'],character=character,restore_equipped=s.enter_dungeon)
            for event in reply:encode_event(event)
            if not _same(s,bound)or not storage.WRITER_ENABLED:raise ValueError('Life late selected source changed')
            return reply


def _capture(s):
    from els_server.domain.fishing_village1500 import _ordinary_binding,_facts
    from els_server.domain.town_travel_flow import _ordinary_actor
    if (not _ordinary_actor(s)or s.account.characters is None or s.account.store.uid!=s.account.uid
            or s.role!='game'or s.phase!='town_ready'or s.active_map!=1500
            or s.account.get_location()['map']!=1500 or not{0x28,0x225,0x227}.issubset(s.completed)
            or s.dungeon_run is not None or getattr(s,'map_synchronizing',False)):
        raise ValueError('Fishing original ready1500 current actor')
    app=getattr(s,'application',None);world=getattr(app,'world',None)
    if world is None:raise ValueError('Fishing original Application town world')
    room=world.room(s);entry=room.get(s)
    if (world.members.get(s)!=(1,1500)or entry is None or entry[0]['uid']!=s.account.uid
            or entry[1]['map']!=1500):raise ValueError('Fishing original1500 town roster')
    return _selection_binding(s),_ordinary_binding(s),_facts(s)


def _current(s,bound):
    try:
        now=_capture(s)
        return bool(_same(s,bound[0])and now[1:]==bound[1:])
    except(ValueError,AttributeError,KeyError,TypeError):return False


def _guard(s,bound):
    def validate(db):
        if not _current(s,bound):raise ValueError('Fishing original source changed')
    return validate


def _encode(events):
    for event in events:encode_event(event)
    return events


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x8b4,0x8b6):return None
    try:bound=_capture(s)
    except(ValueError,AttributeError,KeyError,TypeError):return []
    stop=event.kind==0x8b6
    try:
        if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1
                or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Fishing native request envelope')
        wire.empty_request(event.payload)
        active=getattr(s,'fishing_cycle',None)
        if stop:
            if active is None:return _encode([wire.state_ack(0,stopped=True)])
            if not _current(s,active['binding']):s.fishing_cycle=None;return []
            reply=storage.stop(s.account.store.path,s.account.uid,s.account.account_id,s.shop_session_id,
                active['cycle'],lambda:_encode([wire.state_ack(0,stopped=True)]),_guard(s,bound))
            s.fishing_cycle=None;return reply
        cycle,reply=storage.start(s.account.store.path,s.account.uid,s.account.account_id,s.shop_session_id,
            lambda cycle,state:_encode([wire.state_ack(0),wire.life_notice(state['current'],show_delta=False)]),_guard(s,bound))
        s.fishing_cycle={**cycle,'binding':bound}
        return reply
    except(ValueError,sqlite3.Error,OverflowError):
        if not _current(s,bound):return []
        reply=_encode([wire.state_ack(187,stopped=stop)])
        return reply if _current(s,bound)else[]


def invalidate(s):
    active=getattr(s,'fishing_cycle',None)
    if active is not None and not _current(s,active['binding']):s.fishing_cycle=None


def periodic(s):
    active=getattr(s,'fishing_cycle',None)
    if active is None:return []
    bound=active['binding']
    if not _current(s,bound):s.fishing_cycle=None;return []
    if time.time()<active['deadline']:return []
    try:
        def quest(db,operation):
            from els_server.storage.account_fishing_tasks_scope import record_attempt
            return record_attempt(db,s.account.uid,s.account.account_id,operation,_guard(s,bound))
        result=storage.settle(s.account.store.path,s.account.uid,s.account.account_id,s.shop_session_id,
            active['cycle'],active['serial'],
            lambda caught,used,changes,life,notices:_encode([wire.attempt_notice(0,caught=caught,consumed=used,changes=changes),wire.life_notice(life['current'],show_delta=True),*notices]+([] if used[0][1]>0 and life['current']>=20 and all(value>=40 for _,value in used[1:]) else [wire.state_ack(0,stopped=True)])),
            _guard(s,bound),quest=quest)
        if result['replayed']:
            # A delayed duplicate must never reanimate/reaward/recount8B8.
            s.fishing_cycle=None;return []
        if result['continuable']:
            s.fishing_cycle={**active,'serial':result['serial'],'deadline':result['deadline']}
            return result['reply']
        s.fishing_cycle=None
        return result['reply']
    except(ValueError,sqlite3.Error,OverflowError):
        s.fishing_cycle=None
        if not _current(s,bound):return []
        reply=_encode([wire.state_ack(0,stopped=True)])
        return reply if _current(s,bound)else[]

from els_server.storage.sqlite_timing import write_transaction
