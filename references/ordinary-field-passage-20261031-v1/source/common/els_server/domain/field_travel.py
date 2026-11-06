"""Native ordinary-field passage and return; no monster/reward producer.

Field destinations use 374/375, not town 225/226. Keep the original directed
portals and destination gates; save a town only after its original 227 ready.
The existing Drabaki room and settlement are a separate consumer.
"""
import functools,hashlib,json,sqlite3,struct,uuid
from contextlib import closing
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol import field_boss_messages as wire
from els_server.domain.town_travel_flow import _ordinary_actor
from els_server.domain.town_travel import DestinationRequirementError,entry_failure_code


@functools.lru_cache(maxsize=1)
def catalog():
    root=PROJECT_ROOT/'els_server/data';raw=(root/'field_travel.json').read_bytes()
    meta=json.loads((root/'field_travel.manifest.json').read_bytes());data=json.loads(raw)
    if (meta['schema_version']!=1 or data['schema_version']!=1 or meta['client_sha256']!=CLIENT_SHA
        or data['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=meta['payload_sha256']
        or len(data['fields'])!=meta['fields']):raise ValueError('Ordinary field source identity')
    return data


def _edge(source,destination,position=None):
    return any(p['destination']==destination and (position is None or p['position']==position)
               for p in catalog()['portals'].get(str(source),()))


def _character(s):
    from els_server.storage.seal_quests import load_character
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        return load_character(db,s.account.uid,s.account.account_id)


def _require_field(s,identity):
    row=catalog()['fields'][str(identity)];character=_character(s)
    minimum=max([row['REQUIRE_LEVEL'],*[v['MIN_LEVEL'] for v in row.get('EnableUnitTypeLevel',{}).values()
                                          if v['UNIT_TYPE']==character['unit_type']]])
    if character['level']<minimum:raise DestinationRequirementError('Field minimum level',level=minimum)


def _current(manager,s,room):
    app=getattr(s,'_chip_reset_local_application',None)
    if app is not None and (not s._chip_reset_local_live or app.account is not s.account.root):return False
    return bool(_ordinary_actor(s) and s.role=='game' and s.enter_town and s.item_test
        and s.client_build=='dx11_260923' and not s.dungeon_return_pending
        and getattr(s,'town_warp_transition',None) is None and s.account.characters is not None
        and (room is None and s.phase=='town_ready' and s.active_map==s.account.get_location()['map']
             or room is not None and getattr(room,'ordinary_travel',False)
             and manager.room(s)is room and s.phase=='field_active' and s.active_map==room.identity))


def local_handle(s,event):
    app=getattr(s,'_chip_reset_local_application',None)
    if app is None or app.config.mode!='local':return None
    return handle(app.world.field_bosses,s,event)


def _failure(identity,result=1359):
    return [wire.joined((),None,0,result=result,identity=identity,name='')]


def handle(manager,s,event):
    if event.event_id!=0x202:return None
    room=manager.room(s);ordinary=room is not None and getattr(room,'ordinary_travel',False)
    if event.kind==0x374:
        identity=struct.unpack_from('>i',event.payload)[0]if len(event.payload)>=4 else 0
        if str(identity)not in catalog()['fields']:return _failure(identity)if ordinary else None
        try:
            request=wire.join_request(event.payload,identity_allowed=lambda i:str(i)in catalog()['fields'])
            if (not _current(manager,s,room) or event.performers!=(0,) or event.uid!=event.target_uid
                or event.uid!=2**64-1 or event.payload_mode!=0 or request['members']not in ((),(s.account.uid,))):
                raise ValueError('Ordinary field actor')
            if ordinary and identity==room.identity and event.payload==room.entry_payload:
                return [room.entry_reply]
            source=room.identity if ordinary else s.active_map
            if not _edge(source,identity,request['position']):raise ValueError('Ordinary field portal')
            _require_field(s,identity)
            seed=str(uuid.uuid4());reply=wire.joined((s,),s,uuid.UUID(seed).int%(2**63),identity=identity,
                                                  position=request['position'],name='')
            encode_event(reply)
            if not _current(manager,s,room):raise ValueError('Ordinary field actor changed')
            from els_server.domain.field_boss import FieldRoom
            new=FieldRoom((s,),s,seed,identity=identity)
            new.ordinary_travel=True;new.entry_payload=bytes(event.payload);new.entry_reply=reply
            manager.world.leave(s);manager.rooms[s]=new
            s.phase='field_active';s.active_map=identity;s.pending_map=None
            return [reply]
        except DestinationRequirementError:return _failure(identity,1106)
        except (ValueError,OverflowError):return _failure(identity)
    if not ordinary:return None
    if not _current(manager,s,room):return []
    if event.kind==0x91:
        if len(event.payload)!=8:return []
        progress,mode=struct.unpack('>ii',event.payload)
        if not 0<=progress<=100 or mode!=0:return []
        room.progress[s]=max(progress,room.progress.get(s,0))
        return [Event(0x201,kind=0x92,payload=struct.pack('>iiI',0,progress,0))]
    if event.kind==0x37a:
        if event.payload or room.progress.get(s,0)<100:return [wire.ack(0x37b,1)]
        # The native scene expects its population snapshot after loading. This
        # passage repair does not manufacture monsters, drops or kill rewards.
        room.phase='active';room.loaded.add(s)
        return [wire.ack(0x37b),Event(0x201,kind=0x3d6,payload=bytes(28))]
    if event.kind==0x225:
        requested=struct.unpack_from('>i',event.payload)[0]if len(event.payload)>=4 else 0
        def failure(code=515):return [Event(0x201,kind=0x226,payload=struct.pack('>5i',code,requested,0,0,0))]
        if (event.payload!=struct.pack('>iB',requested,0) or event.performers!=(0,)
            or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
            or not _edge(room.identity,requested)):return failure()
        from els_server.storage.seal_quests import load_character,completed_ids
        from els_server.domain.town_travel import require_destination
        try:
            with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
                db.execute('BEGIN');character=load_character(db,s.account.uid,s.account.account_id)
                records={r[0]for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(s.account.uid,))}
                require_destination(requested,character,completed_ids(db,s.account.uid),records)
            encode_event(Event(0x201,kind=0x226,payload=struct.pack('>5i',0,requested,0,0,0)))
        except (ValueError,OverflowError)as error:return failure(entry_failure_code(error))
        manager.rooms.pop(s);s.phase='map_loading';s.pending_map=None
        # Original town admission/ready owns the location write and all existing
        # inventory/quest restoration. A disconnect here retains the saved town.
        return s.handle(event)
    # Ordinary passage never enters the boss settlement or dungeon reward path.
    if event.kind in (0xad,0x67,0x530,0x535,0x53a,0x53e,0x77a,0x7d4,0x382):return []
    return None
