"""Experimental local business messages from recorded native readers.

The server-list field widths/order are verified; some business semantics remain
unknown. These constructors are only used by the explicit local identity probe.
"""
from els_server.paths import PROJECT_ROOT
import struct,json
from pathlib import Path
from els_server.protocol.protocol_codec import Event

# Native stage-manager mapping: 20000 -> scene 258 -> ruben_village.lua.
LOCAL_TOWN_MAP=20000
LOCAL_TOWN_SCENE=258
LOCAL_WORLD_MAP=30000

def u32(value):return struct.pack('>I',value)
def i32(value):return struct.pack('>i',value)
from els_server.domain.character_stats import combat_attributes
LOCAL_COMBAT_ATTRIBUTES=combat_attributes()
def u16(value):return struct.pack('>H',value)
def wstring(value):
    raw=value.encode('utf-16le');return u32(len(raw))+raw

def client_economy_fields(economy):
    if economy is None:return {}
    if not isinstance(economy,dict):raise ValueError('Invalid client economy')
    ed=economy.get('ed');experience=economy.get('experience')
    if type(ed) is not int or not 0<=ed<=2**63-1:raise ValueError('Client ED bound')
    if type(experience) is not int or not 0<=experience<=2**31-1:raise ValueError('Client experience bound')
    # Updated D9B170 -> 87A6E0: packed 5D Q -> unit+D8 encoded
    # amount; packed 66 i32 -> unit+108 encoded experience. Isolated
    # reward profile only until native re-login evidence is complete.
    return {'0x5d':struct.pack('>Q',ed),'0x66':i32(experience)}

def identity_ack(account_id=1):
    return Event(0x101,kind=0x275,payload=i32(0)+struct.pack('>Q',account_id)+wstring('')+i32(-1)+wstring('')+wstring(''))

def server_endpoints():
    # 0x301cd30: map<int, {int,int,wstring,wstring,ushort,ushort,bool}>.
    record=i32(1)+i32(0)+wstring('本地测试')+wstring('127.0.0.1')+u16(9400)+u16(9401)+b'\x01'
    return Event(0x101,kind=0xd35,payload=u32(1)+i32(1)+record)

def server_summary():
    # 0x3008350 -> 0xcc3490: map key + native packed record (0x8b bytes).
    record=i32(1)+i32(0)+wstring('本地测试')+i32(0)+wstring('127.0.0.1')
    record+=u16(9400)+u16(9401)+i32(0)*4+b'\x01\x01'+wstring('')+i32(0)*2+b'\x01'
    # 0x1cb9720: int selected server, first map, second map (empty).
    return Event(0x101,kind=0x43,payload=i32(1)+u32(1)+i32(1)+record+u32(0))

def channel_list():
    # 13A11F0 consumes two channel maps followed by two eligibility maps.
    # 2C19280 reads each eligibility entry as int key, byte, four ints.
    # New-character auto-entry (137BE30 -> 13A2A50) requires a rule whose
    # range includes level 1 and whose key matches channel record +4.
    # An empty map leaves it selecting -1 after closing the old connection.
    rules=u32(1)+i32(0)+b'\x00'+i32(1)+i32(99)+i32(0)*2
    return Event(0x201,kind=0x491,payload=server_summary().payload[4:]+rules+u32(0))

def character_summary(character=None):
    # Packed native DTO reader RVA 0xcc4da0. Defaults follow 0xcfa120.
    c=character or dict(uid=1001,name='LocalElsword',unit_type=1)
    data=i32(0)+u32(0)+struct.pack('>Q',c['uid'])+wstring(c['name'])
    data+=bytes([0,c['unit_type'],0,0])+struct.pack('>d',0)+b'\x00'+i32(-1)+i32(0)*2
    data+=b'\x00'*3+u32(0)+b'\x09'+i32(-1)+b'\x00'+i32(0)
    return data

def game_login_ack(account_id=1,account_name='local',character=None):
    # Complete 0xcc4140 field order; empty optional containers, one character
    # in 0xcc3b50 -> 0xcfa120 -> 0xcc4da0. Semantic defaults remain experimental.
    profile=struct.pack('>Q',account_id)+wstring(account_name)+wstring('')+i32(0)+b'\x00\x00'
    profile+=wstring('')*2+b'\x00'+wstring('')*2  # 0xcd4c30
    profile+=b'\x00\x00'+wstring('')*3+i32(0)+b'\x00'+wstring('')
    profile+=b'\x00'+u32(0)*2+wstring('')+b'\x00'+wstring('')+u32(0)+b'\x00'
    profile+=i32(0)*3  # 0xcdbdf0
    # Friends without a character have an empty summary map, including login.
    units=u32(0) if account_id!=1 and character is None else u32(1)+i32(0)+character_summary(character)
    extras=units+i32(16)+b'\x00'+u32(0)+i32(0)+struct.pack('>Q',0)+i32(0)
    extras+=u32(0)+u32(0)+i32(0)*3+struct.pack('>Q',0)+i32(0)
    extras+=wstring('')+i32(0)+wstring('')+u32(0)*3
    extras+=u32(0)*2+b'\x00'+wstring('')*2+b'\x00'+u32(0)
    return Event(0x201,kind=0x1f,payload=i32(0)+profile+extras+b'\x00')

def login_configuration():
    # 0x1cb86e0: the configuration notice sets the independently checked
    # +0x53c readiness field. 0x2ff5570 is 28 bytes, 0xcc68e0 is 38 bytes
    # followed by three empty maps; remaining map/set/string are empty.
    return Event(0x201,kind=0x19c,payload=b'\x00'+b'\x00'*28+b'\x00'+u32(0)+wstring('')+b'\x00'*38+u32(0)*4)

def character_list(client_build='legacy',economy=None,characters=None,selection=None):
    if client_build not in ('legacy','dx11_260923'):raise ValueError('Unknown client schema')
    if economy is not None and client_build!='dx11_260923':raise ValueError('Unverified economy schema')
    fixture=json.loads((PROJECT_ROOT/'analysis/character-fixture.json').read_text())
    overrides=client_economy_fields(economy)
    unit=b''.join(overrides.get(field['offset'],bytes.fromhex(field['wire_hex'])) for field in fixture['fields'])
    # 0x2f88180: result, map<int,int>, map<int,vector<Unit>>, string,
    # nested map, string vector, bool, UID map, int vector, nested UID map.
    units=[unit] if characters is None else [character_unit(location=c.get('location'),economy=c.get('economy'),items=c.get('items',[]),character=c) for c in characters]
    if len(units)>16:raise ValueError('Character list capacity')
    data=i32(0)+u32(1)+i32(1)+i32(16)+u32(1)+i32(1)+u32(len(units))+b''.join(units)
    if selection is not None:
        if client_build!='dx11_260923' or characters is None:raise ValueError('Unverified selection schema')
        from els_server.protocol.character_selection_messages import validate_selection
        deployed,order=validate_selection(selection['deployed'],selection['order'],[c['uid'] for c in characters])
    else:deployed,order=(),()
    # 2B4EAA0+95 -> manager+118: deployment vector; +AD -> manager+130:
    # complete order list. 8F3900 requires the latter to cover every character.
    data+=wstring('')+u32(0)+u32(0)+b'\x00'+u32(0)*2
    data+=u32(len(deployed))+b''.join(struct.pack('>Q',uid) for uid in deployed)
    # Updated 2B4EAA0: the three trailing empty counts have matching widths;
    # it then adds list<Q> at AD, int at BD, map<int,{int,int,bool}> at C1.
    # Readers 2BDF150 / 3B6D340 / 2BDF240 require another 12 bytes.
    if client_build=='dx11_260923':data+=u32(len(order))+b''.join(struct.pack('>Q',uid) for uid in order)+i32(0)+u32(0)
    return Event(0x201,kind=0x488,payload=data)

def character_gate_notice():
    # 0x1cbafb0 consumes int result + bool, with no outstanding-wait check.
    # Experimental local account policy: result 0, no additional dialog.
    return Event(0x201,kind=0x327,payload=i32(0)+b'\x00')

def character_unit(location=None,initialize_attributes=False,slots=None,economy=None,items=None,character=None):
    # 0xcc5680, packed DTO constructed by 0x1d09d30. The complete unit
    # precedes these explicit optional fields; native parsing remains the gate.
    fixture=json.loads((PROJECT_ROOT/'analysis/character-fixture.json').read_text())
    fields=[];overrides=client_economy_fields(economy)
    if character is not None:
        from els_server.storage.character_schema import character_uid
        from els_server.domain.character_rules import default_slots,transcendental_stage,artifact_wire
        if slots is None:slots=default_slots(character)
        overrides.update({'0x9':struct.pack('>Q',character_uid(character['uid'])),
                          '0x15':u16(character['unit_class']),
                          '0x17':i32(transcendental_stage(character)),
                          '0x51d':artifact_wire(character),
                          '0x1b':wstring(character['name']),
                          '0x65':bytes([character['level']])})
        from els_server.domain.titles import eligible as title_eligible
        title=character.get('title',0)
        if type(title) is not int or title<0 or title and not title_eligible(character,title):raise ValueError('Native current title input')
        overrides['0x307']=i32(title)
        from els_server.protocol.dungeon_record_messages import completed_map
        overrides['0x10e']=completed_map(character.get('cleared_dungeons',()))
        overrides['0x448']=bytes([bool(character.get('pending_delete',False))])
        overrides['0x449']=struct.pack('>Q',character.get('delete_at',0))
        overrides['0x451']=struct.pack('>Q',character.get('delete_cooldown_until',0))
        if 'profession' in character:
            from els_server.protocol.profession_messages import ProfessionState,state_wire
            overrides['0x3de']=state_wire(ProfessionState(**character['profession']))
        from els_server.domain.ep_points import validate as validate_ep
        # 85BAD0 -> 87A6E0(Unit+48): DTO+54D -> encoded Unit+2950.
        # F5, 2A, D9, career and character-list snapshots share this field.
        overrides['0x54d']=struct.pack('>Q',validate_ep(character.get('ep',0)))
        if 'el_search_collection' in character:
            from els_server.domain.el_search_collection import wire as collection_wire
            overrides['0x482']=collection_wire(character['el_search_collection'])
        if 'normal_fatigue' in character:
            from els_server.protocol.normal_fatigue_messages import fields as normal_fatigue_fields
            overrides.update(normal_fatigue_fields(character['normal_fatigue']))
        if 'life_stamina' in character:
            from els_server.protocol.fishing_messages import life_snapshot
            overrides.update(life_snapshot(character['life_stamina']))
        if 'resonance' in character:
            from els_server.domain.resonance import wire as resonance_wire
            overrides['0x471']=resonance_wire(character['resonance'])
        if economy is not None:
            from els_server.game_data import client_data
            thresholds=client_data().thresholds;level=character['level']
            # 87A6E0 copies DTO AA/AE into Unit+1F0/+208. These are
            # cumulative bounds for the EXP gauge, not per-level rewards.
            overrides['0xaa']=i32(thresholds[level-1])
            overrides['0xae']=i32(thresholds[level] if level<99 else thresholds[-1])
    for field in fixture['fields']:
        data=bytes.fromhex(field['wire_hex'])
        # Updated 87A6E0 copies +0x66 into encoded unit+0x108.
        # The EXP gauge compares this with unit+1F0/+208 thresholds.
        # Preserve prior fixture defaults outside the reward profile.
        # Native 0x7cf51d copies +0xee into encoded unit+0x790 (saved map).
        if field['offset']=='0x66':data=i32(0 if initialize_attributes else 100)
        if (initialize_attributes or character is not None) and field['offset'] in ('0xb6','0xd2'):
            # Base inputs only. The client applies its equipment map, set and
            # passive effects later; sending totals here counts equipment twice.
            data=combat_attributes(character,items)
        if slots is not None and field['reader']=='0xcd7160':
            from els_server.protocol.dungeon_messages import skill_data
            data=skill_data(slots,character)
        if field['offset']=='0xee':
            loc=location or {'map':LOCAL_TOWN_MAP,'board':0,'progress':0}
            data=i32(loc['map'])+bytes([loc['board']])+u16(loc['progress'])+b'\x00'
        if items is not None and field['offset']=='0x12e':
            from els_server.domain.fashion_state import equipment_map
            data=equipment_map(items)
        if items is not None and field['offset']=='0x13e':
            from els_server.protocol.artifact_messages import equipment_map as artifact_equipment_map
            data=artifact_equipment_map(items)
        if field['offset']=='0x30b' and (character or {}).get('guild_membership') is not None:
            from els_server.protocol.guild_membership_messages import saved_membership_wire
            guild=character['guild_membership']
            data=saved_membership_wire(guild['id'],guild['name'],guild['grade'],data)
        fields.append(overrides.get(field['offset'],data))
    return b''.join(fields)

def player_initialization(location=None,initialize_attributes=False,economy=None,items=None,character=None,*,restore_equipped=False):
    unit=character_unit(location,initialize_attributes,economy=economy,items=items,character=character)
    data=i32(0)+unit+wstring('')+struct.pack('>Q',0)+wstring('')
    from els_server.domain.inventory_items import inventory_restore_map
    from els_server.domain.bag_capacity import capacity_map
    from els_server.protocol.bank_messages import restore_map as bank_restore_map
    inventory=bank_restore_map(items or [],(character or {}).get('bank_items',[]))
    if restore_equipped:
        # 1385780 restores Unit equipment first, then 8695F0 -> 197D140
        # clears the inventory manager while setting capacities. Rebuild the
        # owned worn instances in the following 2A inventory map as well.
        # Keeping only Unit's equipped UID vector leaves dungeon models bare.
        from els_server.domain.fashion_state import record
        worn=sorted((i for i in items or [] if i['group']==9),key=lambda i:i['uid'])
        inventory=u32(struct.unpack_from('>I',inventory)[0]+len(worn))+inventory[4:]+b''.join(struct.pack('>Q',i['uid'])+record(i) for i in worn)
    from els_server.storage.resurrection_counter import validate_count as known_resurrection_count
    known_c=known_resurrection_count((character or {}).get('known_resurrection_count',0))
    data+=capacity_map(character)+inventory+i32(known_c)+i32(0)+wstring('')+u32(0)*2+b'\x00'
    data+=u32(0)+b'\x00'+i32(0)*2
    # 0xcdd450: byte, UID, two strings, two UIDs, byte, UID, three bytes.
    data+=b'\x00'+struct.pack('>Q',0)+wstring('')*2+struct.pack('>QQ',0,0)
    data+=b'\x00'+struct.pack('>Q',0)+b'\x00'*3
    from els_server.protocol.character_custom_messages import owned_map as custom_owned_map
    data+=u32(0)+custom_owned_map((character or {}).get('character_custom',{}).get('owned',{}))+b'\x01'+u32(0)  # DTO+6A8 owned custom map; +6B8 ctor true
    # Current DA3370 has THREE DB6FA0 records; each includes a final bool.
    # The legacy two-record tail made the native reader return false.
    data+=(u32(0)+b'\x00'+struct.pack('>f',0)+b'\x00')*3
    return Event(0x201,kind=0x2a,payload=data)

def inventory_initialization():
    # Legacy function name. Current 2B/DA3620 initializes quest/timed state,
    # not bag contents. Saved bags are in player_initialization()'s 2A map.
    return Event(0x201,kind=0x2b,payload=i32(0)+u32(0)*6)

def skill_slots_initialization(slots=None,uid=1001,character=None):
    from els_server.domain.skill_state import DEFAULT_SLOTS,initialization_payload
    from els_server.domain.character_rules import default_slots
    from els_server.domain.skill_rules import equippable_skills,learned_skills,upgraded_slots
    return Event(0x201,kind=0x55b,payload=initialization_payload(default_slots(character) if slots is None else upgraded_slots(slots,character),uid,equippable_skills(character),learned_skills(character),character))

def optional_player_initializations(initialize_health=False,uid=1001,*,health_max=100,luciel_active=0,wardrobe=None,wardrobe_favorites=(),tutorial_pending=False):
    if type(health_max) is not int or not 1<=health_max<2**31:raise ValueError('Initial health maximum')
    if type(luciel_active) is not int or luciel_active not in (0,1):raise ValueError('Initial LuCiel selector')
    # All counts are empty; fixed nested records retain their actual field widths.
    # 0x2c -> 0xb211a0, 0x2d -> 0x1cec6a0, 0x2e -> 0xcd77f0.
    messages=[Event(0x201,kind=0x2c,payload=i32(0)+u32(0)*2),
              Event(0x201,kind=0x2d,payload=i32(0)+struct.pack('>Q',uid)+u32(0)*5),
              Event(0x201,kind=0x2e,payload=i32(0)*4+struct.pack('>Q',0)+u32(0))]
    # 0xcc5d90, including fixed 0xcc43e0, 0xb8af80, 0xcd8f40,
    # 0xcdd780 and 0xcdd800; this is a local empty-state fixture.
    profile=b'\x00'+wstring('')+u32(0)+b'\x00'+u32(0)+struct.pack('>QQ',0,0)+wstring('')*3+b'\x00'
    flags=b'\x00'+i32(0)*8  # 0xb8af80
    data=i32(0)+b'\x00'+u32(0)+profile+flags+b'\x00\x00'
    # CC5D90+15B enables the tutorial room request (60), not ordinary solo
    # dungeon control. The caller supplies a read-only owned first-entry check.
    data+=i32(0)*6+u32(0)*3+i32(0)*2+bytes((bool(tutorial_pending),))+i32(0)+struct.pack('>Q',0)
    data+=u32(0)*4+i32(0)+u32(0)+b'\x00'+i32(0)+i32(0)*2+i32(0)+struct.pack('>Q',0)+u32(0)
    data+=b'\x00\x00'+i32(0)+u32(0)+b'\x00'+u32(0)*2
    messages.append(Event(0x201,kind=0x30,payload=data))
    # 0xcc5ab0: vector, fixed ten bytes, bool, UID, four vectors,
    # two maps, vector, string, byte, vector, three strings, integer enum.
    data=i32(0)+u32(0)+bytes(10)+b'\x00'+struct.pack('>Q',0)
    data+=u32(0)*7+wstring('')+b'\x00'
    # CC5AB0+E8 -> CD97E0/CD8020/CF5950/CBE9E0. 13126B0 reads
    # max HP at 0, current HP at 4, max MP at 8, current MP at C.
    # 786380 saves HP/current maximum; 131F080 separately saves MP fraction.
    # Use the same local HP input as the fresh character's attributes.
    # Lu/Ciel's entry consumes the absolute current HP, rather than only
    # retaining the HP fraction. MP retains the existing 100/100 policy.
    stats=i32(health_max)*2+i32(100)*2+i32(0)+bytes(2)+i32(0)+u32(0)*5+i32(0)*2+bytes((luciel_active,0,0,0))
    data+=u32(1)+stats if initialize_health else u32(0)
    data+=wstring('')*3+i32(0)
    messages.append(Event(0x201,kind=0x2f,payload=data))
    from els_server.protocol.wardrobe_messages import initialization as wardrobe_initialization
    messages.append(wardrobe_initialization(wardrobe or {},wardrobe_favorites))
    return messages

def key_bindings_initialization(bindings=bytes(12)):
    # 1cbf340 -> three cdde60 maps<short,short>; empty keyboard map uses
    # the native 41d250 reset/default branch, followed by 656eb0/656bf0.
    from els_server.domain.key_bindings import validate_bindings
    return Event(0x201,kind=0x399,payload=i32(0)+validate_bindings(bindings))

def connection_ack(port_probe_port=1):
    # DX11 1394340 stores field 2 at globals+14C; 1395F70 uses it as
    # the UDP discovery port. The former placeholder 1 caused ten retries.
    if type(port_probe_port) is not int or not 1<=port_probe_port<=65535:
        raise ValueError('Invalid UDP discovery port')
    return Event(0x201,kind=0x1b,payload=i32(0)+i32(port_probe_port)+i32(0))


def responses(kind,client_build='legacy',*,account_id=1,account_name='local',character=None):
    if kind==0x274:return [identity_ack(account_id)]
    if kind==0xd33:return [Event(0x101,kind=0xd34,payload=i32(0)),server_endpoints()]
    if kind==0x41:return [Event(0x101,kind=0x42,payload=i32(0)),server_summary()]
    if kind==0x1a:return [connection_ack()]
    if kind==0x1e:return [game_login_ack(account_id,account_name,character),login_configuration()]
    if kind==0x48d:return [Event(0x201,kind=0x48f,payload=struct.pack('>Q',account_id)+u32(0))]
    if kind==0x35:return [Event(0x201,kind=0x36,payload=i32(0))]
    if kind==0x1ef:
        if client_build=='dx11_260923':
            from els_server.protocol.session_clock import session_clock_ack
            return [session_clock_ack()]
        return [Event(0x201,kind=0x1f0,payload=wstring('')+struct.pack('>QQQI',0,0,0,0)+bytes(16))]
    if kind==0x39:return [Event(0x201,kind=0x3a,payload=i32(0)+wstring('')+u16(0)+wstring('')*2+b'\x00'+wstring('')*2)]
    if kind==0x485:return [character_list(client_build)]
    if kind==0x490:return [channel_list()]
    if kind==0x233:return [Event(0x201,kind=0x234)]
    return []
