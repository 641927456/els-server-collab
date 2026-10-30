"""Pinned native dungeon codecs and gated friends-party admission rosters."""
from els_server.paths import PROJECT_ROOT
import json,struct
from pathlib import Path
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32,u32,wstring,LOCAL_COMBAT_ATTRIBUTES
from els_server.domain.skill_state import DEFAULT_SLOTS,record,validate_slots
SUPPORTED_DUNGEON=30000  # Loaded definition: 鑹惧皵涔嬫爲.

def skill_data(slots,character=None):
    from els_server.domain.skill_rules import equippable_skills,learned_skills,upgraded_slots
    allowed=equippable_skills(character);ranks=learned_skills(character)
    from els_server.domain.skill_expansion import records
    slots=validate_slots(upgraded_slots(slots,character),allowed,character);learned=u32(len(ranks))+b''.join(record(v,level) for v,level in ranks.items())
    from els_server.domain.skill_traits import map_wire
    from els_server.domain.skill_state import preset_payload
    preset=preset_payload(slots,allowed,character)
    from els_server.domain.skill_unlocks import ids_wire
    force_owned=learned  # Preserve the existing non-owner wire format.
    if (character or {}).get('force_inventory'):
        from els_server.domain.boosting_2026_force_inventory import vector
        force_owned=vector(character)
    return u32(22)+b''.join(record(v) for v in slots)+records(character)+learned+u32(0)+ids_wire(character)+b'\1\1'+preset+force_owned+b'\0'

def member(slots,character=None,items=None,*,account_id=None,peer_port=None,capture=None):
    from els_server.domain.character_stats import combat_attributes
    data=json.loads((PROJECT_ROOT/'analysis/dungeon-member-fixture.json').read_text())
    overrides={}
    if items is not None:
        # Current DB0AC0 is also character_unit's verified equipped-slot map.
        # 87CAF0 restores this first map into remote UserInfo. A remote actor
        # cannot reuse the local player's previously initialized equipment.
        from els_server.domain.fashion_state import equipment_map
        overrides['0x1eb']=equipment_map(items)
    if account_id is not None:
        if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('Dungeon account identity')
        overrides.update({'0xcc':struct.pack('>Q',account_id),'0xd4':struct.pack('>Q',account_id)})
    if peer_port is not None:
        if type(peer_port) is not int or not 21100<=peer_port<=21105:raise ValueError('Dungeon loopback peer endpoint')
        # D9D2F0 -> 87CAF0 copies 117/137 and 139/159 to UserInfo+60/80
        # and +88/A8. D8B620 passes these to 486DA0's public/internal UDP
        # addresses. All game datagrams stay at this client's local bridge.
        overrides.update({'0x117':wstring('127.0.0.1'),'0x137':struct.pack('>H',peer_port),
                          '0x139':wstring('127.0.0.1'),'0x159':struct.pack('>H',peer_port)})
    if character is not None:
        from els_server.domain.character_rules import transcendental_stage
        from els_server.game_data import client_data
        unit=client_data().unit(character['unit_class'])
        from els_server.domain.titles import eligible as title_eligible
        title=character.get('title',0)
        if type(title) is not int or title<0 or title and not title_eligible(character,title):raise ValueError('Native current title input')
        overrides['0x3ef']=i32(title)
        # Real persisted characters carry unit_type. The lookup fallback only
        # preserves older callers that supplied a class-only fixture.
        unit_type=character.get('unit_type',unit['unitType'])
        if type(unit_type) is not int or unit_type!=unit['unitType']:
            raise ValueError('Dungeon character template/class mismatch')
        overrides.update({'0xe1':struct.pack('>Q',character['uid']),'0xe9':i32(unit_type),'0xed':struct.pack('>H',character['unit_class']),
                   '0xef':i32(transcendental_stage(character)),'0xf3':wstring(character['name']),'0x193':bytes([character['level']])})
    if character is not None and character.get('unit_type')==10:
        from els_server.protocol.luciel_messages import preference,active_preference
        overrides['0x1d0']=bytes([active_preference(character)])
        overrides['0x1d1']=bytes([preference(character)])
        if capture is not None:
            # Actor gauge initialization consumes absolute HP; the remaining six
            # inputs carry the same equipped totals as the ordinary member path.
            from els_server.domain.character_stats import combat_values
            hp=struct.pack('>f',combat_values(character,items)[0])
            for key in ('0x198','0x1b4'):overrides[key]=hp+combat_attributes(character,items)[4:]
    parts=[overrides.get(f['offset'],skill_data(slots,character) if f['reader']=='0xcd7160' else combat_attributes(character,items) if f['reader']=='0xcd6df0' else bytes.fromhex(f['wire_hex'])) for f in data['fields']]
    payload=b''.join(parts)
    if capture is not None:
        spans={};offset=0
        for field,part in zip(data['fields'],parts):
            if field['offset'] in ('0x198','0x1b4','0x1d1'):spans[field['offset']]=(offset,len(part))
            offset+=len(part)
        capture(payload,spans)
    return payload

def room_info(dungeon_id=SUPPORTED_DUNGEON,*,room_id=10001,name='LocalSingle',bootstrap_port=None):
    from els_server.game_data import client_data
    if type(dungeon_id) is not int:raise ValueError('Dungeon identity')
    client_data().dungeon(dungeon_id)
    # CBDCC0, preserving constructor sentinels; B2 is the native map ID.
    data=b'\1'+struct.pack('>Q',room_id)+u32(0)+wstring(name)
    # Current D9BCC0 -> 909B60 -> 487C90 consumes this endpoint.
    if bootstrap_port is not None and (type(bootstrap_port) is not int or not 1<=bootstrap_port<=65535):raise ValueError('Dungeon bootstrap port')
    data+=b'\0\1\0'+wstring('')+b'\0\0'+wstring('127.0.0.1' if bootstrap_port is not None else '')+struct.pack('>H',bootstrap_port or 0)+wstring('')
    data+=b'\0\xff\0'+i32(-1)+b'\0\0'+i32(0)+bytes(4)+bytes(8)+i32(0)
    # 11C99A0 creates byte mode from Party+40 (native clear record byte 6),
    # which is 0. 7D4's mode=1 chooses solo matching, not this room mode.
    from els_server.domain.native_hero_inputs import difficulty
    data+=bytes((difficulty(dungeon_id),))+i32(dungeon_id)+b'\0\0'+bytes(8)*2+i32(0)+b'\0'
    data+=u32(0)+bytes(2)+i32(0)+b'\0\0'+bytes(8)+u32(0)
    data+=b'\0'+i32(0)+bytes(8)*2
    return data

def dungeon_start(slots=DEFAULT_SLOTS,character=None,items=None,dungeon_id=SUPPORTED_DUNGEON,*,room_id=10001,account_id=None,bootstrap_port=None,member_capture=None):
    # 2f867a0: ushort, room, two vectors<CC0050>, name,
    # vector<CDA160 metadata records>, vector<ten floats>, vector<int>.
    # CC0050 byte 2 -> native slot+9E. 1360320 binds this member as
    # the dungeon master actor (+2E0 UID / +BA0 reference).
    # Master selection 1360490 includes 3..5; actor creation 135DF20
    # excludes 1..3. Type 4 satisfies both native branches (0 loses master).
    team=b'\0\4\1'+bytes(3)+i32(0)+u32(1)+member(slots,character,items,account_id=account_id,capture=member_capture)+u32(0)+bytes(4)
    from els_server.domain.native_hero_inputs import factor_vector
    payload=bytes(2)+room_info(dungeon_id,room_id=room_id,bootstrap_port=bootstrap_port)+u32(1)+team+u32(0)+wstring('')+u32(0)+factor_vector(dungeon_id)+u32(0)
    return Event(0x201,kind=0x14a,payload=payload)


def party_dungeon_start(members,leader,identity,room_id,*,bootstrap_port=None,member_captures=None):
    """One native slot per participant. Peer transport is configured separately.

    Current D9DDB0 reads a vector of member DTOs per slot. The first member
    identifies that slot's actor; placing the whole party in one slot loses
    the other actors. Native scene/peer acceptance still requires GUI testing.
    """
    from els_server.domain.raid_party import raid_definition
    source=raid_definition(identity)
    maximum=source['maximum'] if source else 4
    from els_server.domain.dungeon_routes import route_catalog
    if str(identity) in route_catalog()._data['internal_routes']:
        from els_server.game_data import client_data
        maximum=min(6,client_data().dungeon(identity)['m_MaxPlayerCount'])
    if not 2<=len(members)<=maximum or leader not in members:raise ValueError('Dungeon party size/leader')
    teams=[];captured={}
    for index,s in enumerate(members):
        master=s is leader
        # Use the same verified absolute-HP initialization as solo admission.
        # Collect actual roster bytes without mutating a playable session.
        def capture(payload,spans):captured[s]=(payload,dict(spans))
        body=member(s.account.get_skills(),s.account.character(),s.account.get_inventory_snapshot()['items'],account_id=s.identity['id'],peer_port=21100+index,capture=capture)
        teams.append(bytes([index,4,int(master)])+bytes(3)+i32(0)+u32(1)+body+u32(0)+bytes(4))
    from els_server.domain.native_hero_inputs import factor_vector
    payload=bytes(2)+room_info(identity,room_id=room_id,name='Friends',bootstrap_port=bootstrap_port)+u32(len(teams))+b''.join(teams)+u32(0)+wstring('')+u32(0)+factor_vector(identity)+u32(0)
    if member_captures is not None:member_captures.update(captured)
    return Event(0x201,kind=0x14a,payload=payload)

def initial_substage(client_build='legacy',npc_key=None,gate_test=False):
    # B511F0 case B2 -> B57400 -> 2F865C0. Native substage index 0,
    # metadata integer, spawn map, geometry map, float, bool, three maps,
    # two ints, and three more maps. The spawn map replaces resource NPC lists.
    if client_build not in ('legacy','dx11_260923'):raise ValueError('Unknown dungeon schema')
    spawns=u32(0)
    if client_build=='dx11_260923':
        # Observed stream mode 0: opaque string BEFORE the NPC vector.
        # Original 2B42890 decoded all scalar fields and consumed 116 bytes
        # in the isolated native check 20261013-042122 (no game mutation).
        from els_server.domain.dungeon_npcs import updated_spawn_map
        spawns=updated_spawn_map(npc_key)
    npc_init=u32(0)
    if client_build=='dx11_260923':
        # DTO+65 -> Game v4D8 -> Game+F98: per-NPC initialization data.
        # 2BDEB50 consumed the complete 172-byte candidate in the original
        # reader, including native template 88 and its resource names;
        # labels of its stat scalars are still under investigation.
        from els_server.domain.dungeon_npcs import updated_npc_init_map
        npc_init=updated_npc_init_map(npc_key)
    if gate_test:
        if client_build!='dx11_260923' or npc_key!=0:raise ValueError('Gate test requires isolated slot0 profile')
        from els_server.domain.dungeon_npcs import gate_test_maps
        spawns,npc_init=gate_test_maps()
    payload=i32(0)*2+spawns+u32(0)+struct.pack('>f',0)+b'\0'+u32(0)*3+i32(0)*2+npc_init+u32(0)*2
    return Event(0x201,kind=0xb2,payload=payload)

def initial_part(part=0):
    # B511F0 B7 reads one signed byte; game v5F0 F70050 forwards it to
    # v5C0 F6C1F0, selecting resource part 0 and constructing its runtime.
    # BD must follow this: F6C8B0 returns early when no part is selected.
    if type(part) is not int or not 0<=part<128:raise ValueError('Dungeon part')
    return Event(0x201,kind=0xb7,payload=struct.pack('>b',part))

def begin_substage(part=0,*,npc_entries=()):
    # B511F0 case BD -> state v610 B58B20 -> B7B970 reader:
    # byte, bool, byte, vector<byte>, int. Game v620 F70470 invokes
    # v5D0 F6C8B0, which clears Game+620 and resumes actor updates.
    # Map 30000 does not consume the final timer (only A258/A29E do).
    if type(part) is not int or not 0<=part<128:raise ValueError('Dungeon part')
    # Current 1044D70 passes DTO+3 to 1076D70 / 1AEB4C0.
    # The existing client fills Game+1060 and translates death IDs itself.
    from els_server.protocol.npc_uid_map import uid_translation_vector
    return Event(0x201,kind=0xbd,payload=struct.pack('>b',part)+bytes(2)+uid_translation_vector(npc_entries)+i32(-1))

def end_ack():
    # Updated C504D0 / 2BDE570: i32*3, bool, nested i32*2,
    # list<Q>, bool*2, u16, bool*2. Original reader consumed all 31 bytes.
    return Event(0x201,kind=0x68,payload=bytes(31))

def return_user_sync(location,slots,economy=None,items=None,character=None,*,inventory_updates=None):
    # Updated C4DDF0: complete D9B170 unit, inventory vector,
    # map<int,int>, bool. Native isolated parse consumed 1030 bytes,
    # UID1001 and saved town 20000. Its inventory vector is an acquisition
    # delta (197DAD0), not a restoration snapshot; default to no bag updates.
    from els_server.protocol.local_messages import character_unit
    from els_server.domain.inventory_items import inventory_payload
    updates=[] if inventory_updates is None else inventory_updates
    bag=u32(0) if updates is None else inventory_payload([i for i in updates if i['group']!=9])
    return Event(0x201,kind=0xd9,payload=character_unit(location,True,slots,economy,items,character)+bag+u32(0)+b'\0')


def luciel_hp_notification(source,health_max,style):
    """Patch the actual admitted member; preserve every unrelated wire byte.

    In particular the cached numeric field at DTO5C8 is opaque and retained.
    No power, current HP/MP, skill, equipment or timer state is invented here.
    The original70D consumer only restores its two attribute groups/style,
    clamps HP and refreshes existing native effects;105 owns slot removal.
    """
    uid,payload,spans=source
    from els_server.storage.character_schema import character_uid
    from els_server.protocol.luciel_messages import style as valid_style
    character_uid(uid);valid_style(style)
    if not isinstance(payload,bytes) or set(spans)!=set(('0x198','0x1b4','0x1d1')):raise ValueError('Admitted LuCiel HP source')
    if not isinstance(health_max,(int,float)) or not 0<health_max<=1e12:raise ValueError('LuCiel HP maximum')
    updated=bytearray(payload);hp=struct.pack('>f',health_max)
    for key in ('0x198','0x1b4'):
        offset,size=spans[key]
        if size!=28 or not 0<=offset<=len(payload)-size:raise ValueError('Admitted HP field span')
        updated[offset:offset+4]=hp
    offset,size=spans['0x1d1']
    if size!=1 or not 0<=offset<len(payload):raise ValueError('Admitted style field span')
    updated[offset]=style
    return Event(0x201,kind=0x70d,payload=bytes(updated))
