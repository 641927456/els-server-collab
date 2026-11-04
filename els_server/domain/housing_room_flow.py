"""Finite normal923 own-room entry, exact actor binding and original town return."""
from contextlib import closing
from pathlib import Path
import json,math,sqlite3,struct
from els_server.domain.town_travel_flow import _ordinary_actor
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.housing_messages import entry_request,entry_snapshot
from els_server.storage import housing_rooms as storage

def local_application(s):
    # Standalone sessions intentionally have no .application/friends identity.
    # Use the existing App-created local witness and current selected graph;
    # never fabricate friends membership or relax the friends branch below.
    from els_server.domain.equipment_chip_flow import reset_authority
    reset_authority(s)
    app=getattr(s,'_aux_local_application',None)
    if(getattr(s,'application',None)is not None or app is None
       or app is not getattr(s,'_chip_reset_local_application',None)
       or getattr(s,'_aux_local_live',None)is not True
       or s not in app._aux_local_sessions or app.config.mode!='local'
       or app.registry is not None or s.account.root is not app.account):raise ValueError('Housing trusted standalone local actor')
    return app

def local_identity(s):
    app=local_application(s);a=s.account;root=a.root;path=Path(a.store.path).resolve()
    if(s.role!='game'or not s.enter_town or not s.item_test or s.client_build!='dx11_260923'
       or s.dungeon_return_pending or not{0x28,0x225,0x227}.issubset(s.completed)
       or Path(a.characters.path).resolve()!=path or Path(app.config.state_file).resolve()!=path):raise ValueError('Housing current local native actor')
    refs=(a,a.store,a.characters,root,app,root.character_accounts,root.store,app.config,app._aux_local_sessions,app.world,s.dungeon_run)
    values=(a.uid,a.account_id,s.shop_session_id,root.account_id,a.characters.account_id,str(path),
            s.role,s.client_build,s.item_test,s.enter_town,s.dungeon_return_pending,
            s._aux_local_live,s._chip_reset_local_live,json.dumps(a.get_location(),sort_keys=True))
    return refs,values

def identity(s):
    if getattr(s,'application',None)is None:return local_identity(s)

    if(not _ordinary_actor(s)or getattr(s,'application',None)is None or s.account.characters is None
       or s.role!='game'or not s.enter_town or not s.item_test or s.client_build!='dx11_260923'
       or s.dungeon_return_pending or not{0x28,0x225,0x227}.issubset(s.completed)):raise ValueError('Housing current ordinary native actor required')
    a=s.account;app=s.application;root=a.root;world=app.world
    if (type(s.identity)is not dict or s.identity.get('id')!=a.account_id
            or root.root is not root or root.characters is not a.characters
            or root.account_id!=a.account_id or a.characters.account_id!=a.account_id
            or world.dungeons.world is not world):raise ValueError('Housing actual application/owner world')
    path=Path(a.store.path).resolve()
    if path!=Path(a.characters.path).resolve()or path!=Path(app.config.state_file).resolve():raise ValueError('Housing actor application database')
    # Retain actual references, including the root/application/selected world
    # graph. Normal world.synchronize changes town contents after admission,
    # so town membership/room entries are captured separately per request.
    refs=(a,a.store,a.characters,root,app,root.character_accounts,getattr(root,'store',None),
          app.config,app.accounts,app.playing,s.identity,app.registry,world,world.dungeons,
          world.members,world.towns,world.dungeons.room(s),s.dungeon_run)
    values=(a.uid,a.account_id,s.shop_session_id,root.account_id,a.characters.account_id,
            str(path),str(Path(app.registry.path).resolve()),json.dumps(s.identity,sort_keys=True),
            s.role,s.client_build,s.item_test,s.enter_town,s.dungeon_return_pending,
            getattr(s,'released',False),getattr(s,'social_overflow',False),getattr(s,'coop_error',None),
            json.dumps(a.get_location(),sort_keys=True))
    return refs,values

def world_state(s):
    if getattr(s,'application',None)is None:
        app=local_application(s)
        return(app,app._aux_local_sessions,app.world,s.dungeon_run),(app.config.mode,s in app._aux_local_sessions,frozenset(s.completed))
    world=s.application.world;key=world.members.get(s);room=world.towns.get(key)
    entry=None if room is None else room.get(s)
    return (world.dungeons.room(s),room,entry),(key,frozenset(s.completed),repr(entry))

def scene(s,source,context):
    if getattr(s,'application',None)is None:
        app=local_application(s);world=app.world
        if(world.dungeons.room(s)is not None or s in world.members or any(s in room for room in world.towns.values())):raise ValueError('Standalone housing cannot borrow friends membership')
        if s.phase not in('town_ready','housing_ready')or s.account.get_location()['map']!=source:raise ValueError('Housing standalone source scene')
        return
    world=s.application.world
    if world.dungeons.room(s)is not None:raise ValueError('Housing cannot bypass current dungeon room')
    if context is None:
        key=(1,source);entry=world.towns.get(key,{}).get(s)
        if (world.members.get(s)!=key or entry is None or entry[0].get('uid')!=s.account.uid
                or entry[1].get('map')!=source):raise ValueError('Housing requires actual completed source town membership')
    elif world.members.get(s)is not None or any(s in room for room in world.towns.values()):
        raise ValueError('Housing admitted actor must have normally left ordinary town')

def handle(s,event,sequence):
    context=getattr(s,'housing_own_room',None)
    if event.event_id!=0x202 or(event.kind!=0x923 and not(context is not None and event.kind in(0x225,0x227))):return None
    try:refs,values=identity(s);world_refs,world_values=world_state(s)
    except(ValueError,AttributeError,KeyError,TypeError):return []
    phase=s.phase;active=s.active_map;pending=s.pending_map
    def same():
        try:r,v=identity(s);wr,wv=world_state(s)
        except(ValueError,AttributeError,KeyError,TypeError):return False
        return (v==values and all(a is b for a,b in zip(r,refs))and wv==world_values
                and all(a is b for a,b in zip(wr,world_refs))
                and(s.phase,s.active_map,s.pending_map)==(phase,active,pending))
    def failed():
        if not same():return []
        try:
            value=storage.dto(s.account.character());value['000']=-1
            answer=[Event(0x201,kind=0x924,payload=entry_snapshot(value))]if event.kind==0x923 else[Event(0x201,kind=0x228,payload=struct.pack('>i',-1))]if event.kind==0x227 else[Event(0x201,kind=0x226,payload=struct.pack('>iiiii',-1,0,0,0,0))]
            for reply in answer:encode_event(reply)
        except(ValueError,OverflowError):return []
        return answer if same()else[]
    try:
        if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
           or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Housing native envelope')
        source=s.account.get_location()['map']
        operation=values[2]+':housing923:'+str(values[0])+':'+str(sequence)
        if context is None:
            if phase!='town_ready'or active!=source or pending!=source or getattr(s,'town_warp_transition',None)is not None:raise ValueError('Housing stable source town required')
        else:
            if(any(a is not b for a,b in zip(context['refs'],refs))or context['values']!=values or phase!='housing_ready'or active!=26000 or pending!=26000 or context['source_town']!=source):raise ValueError('Housing current admission generation required')
        scene(s,source,context)
        def guard(db):
            if not same():raise ValueError('Housing actor changed before commit')
            if db.execute('SELECT town FROM location WHERE uid=?',(values[0],)).fetchone()!=(source,):raise ValueError('Housing SQL source town changed')
            from els_server.storage.item_actor import require_active_character
            require_active_character(db,values[0]);storage.housing_access.owner(db,values[0],values[1])
        if event.kind==0x923:
            request=entry_request(event.payload)
            if request['kind']!=1 or request['target']!=0:raise ValueError('Housing visits/random are outside finite own room')
            if context is not None and(context['operation']!=operation or context['payload']!=event.payload):raise ValueError('Already admitted own room')
            result=storage.enter(refs[1].path,values[0],values[1],event.payload,operation,values[2],source,guard)
            if not same():return []
            # SQL+all encoding have committed. These in-memory assignments do
            # not perform another write or alter the last ordinary login town.
            s.housing_own_room=dict(refs=refs,values=values,operation=operation,payload=event.payload,generation=result['generation'],source_town=source)
            s.phase='housing_ready';s.active_map=26000;s.pending_map=26000
            return result['events']
        if context is None:raise ValueError('Housing admission is missing')
        with closing(sqlite3.connect(Path(refs[1].path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            db.execute('BEGIN');guard(db)
            row=db.execute('SELECT owner,account_id,session_id,generation,source_town FROM housing_room_admissions WHERE operation_id=?',(context['operation'],)).fetchone()
            if row!=(values[0],values[1],values[2],context['generation'],source):raise ValueError('Housing durable admission changed')
            if event.kind==0x227:
                from els_server.storage.local_state import scene_ready_location
                board,progress,xyz=scene_ready_location(event.payload)
                if not 0<=board<255 or not 0<=progress<=100 or any(not math.isfinite(v)or abs(v)>1000000 for v in xyz):raise ValueError('Housing scene readiness fields')
                answer=[Event(0x201,kind=0x228,payload=bytes(4))]
                for reply in answer:encode_event(reply)
                guard(db);return answer
            if event.payload!=struct.pack('>iB',source,0):raise ValueError('Housing return must use original source town')
            guard(db)
        # Delegate only the original town225/227 flow. Source1011/1012 gates
        # receive their actual saved source, with no new town alias or fee.
        s.phase='town_ready';s.active_map=source;s.pending_map=source;s.housing_own_room=None
        return None
    except(ValueError,sqlite3.Error,OverflowError,KeyError,AttributeError,TypeError):return failed()
