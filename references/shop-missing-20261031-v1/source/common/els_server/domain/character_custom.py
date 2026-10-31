"""Native permanent custom books and career-qualified free selections."""
import functools,hashlib,json
from pathlib import Path

DATE1='2001-01-01 00:00:00'
DATE2='2050-01-01 00:00:00'
SLOT_TYPES={1:1,2:2,3:3,4:3,5:3,6:3,7:7,8:7,10:1,11:1,12:1,13:7,14:7,15:15,19:19,20:20,21:20,22:20,23:20,24:24,25:24,26:24,27:24}
FACE_UNITS=frozenset(range(1,16))
COUNTS={1: 1039, 2: 379, 3: 386, 7: 1485, 15: 40, 24: 71, 19: 195, 20: 897}
SOURCE_COUNTS={1: 858, 2: 386, 3: 246, 7: 1502, 15: 40, 24: 71, 19: 0, 20: 0}
FREE_EMOTES=frozenset({17000,17033,17034,17035,17036})

@functools.lru_cache(maxsize=1)
def data():
    raw=(Path(__file__).parents[1]/'data/character_custom_permanent.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='41d413b7a0a1274f4c5e794dfb44cf414f3435d033db60c82e01c36050a42f3e':raise ValueError('Permanent custom catalog source changed')
    return json.loads(raw)

@functools.lru_cache(maxsize=1)
def catalog():
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    rules={}
    for row in data()['books']:
        if row['book'] in rules or row['type'] not in COUNTS or not row['units'] or set(row['units'])-FACE_UNITS or row['book']not in VERIFIED_TEMPLATES or TEMPLATE_BAG_GROUPS[row['book']]!=4:raise ValueError('Permanent custom source qualification')
        rules[row['book']]=row
    if {k:sum(r['type']==k for r in rules.values())for k in COUNTS}!=SOURCE_COUNTS:raise ValueError('Permanent custom family coverage')
    return rules

@functools.lru_cache(maxsize=1)
def custom_rules():
    return {r['custom_id']:r for r in data()['customs']}

def registered_units(family):
    if family not in COUNTS:raise ValueError('Unsupported custom family')
    from els_server.game_data import client_data
    return frozenset({u for r in catalog().values()if r['type']==family for u in r['units']}|{client_data().unit(r['unit_class'])['unitType']for r in data()['free_customs']if r['type']==family})

def canonical(custom_id,*,variant=None,ability=0):
    if type(custom_id)is not int:raise ValueError('Custom ID')
    row=custom_rules().get(custom_id)
    if custom_id not in ({0}|FREE_EMOTES) and row is None:raise ValueError('Unqualified custom ID')
    expected=row.get('variant',1)if row else 1
    if variant is None:variant=expected
    if type(variant)is not int or (variant not in (1,2,3)if custom_id==0 else variant!=expected):raise ValueError('Custom side variant')
    if type(ability)is not int or (ability and (row is None or row['type']not in(3,15)or ability not in socket_options(row['ability_group']))):raise ValueError('Custom ability option')
    return dict(custom_id=custom_id,ability=ability,date1=DATE1,date2=DATE2,variant=variant)

def socket_options(group):
    if group is None:group=0
    rows=data()['socket_options']
    return set(rows[str(group)]if isinstance(rows,dict)and str(group)in rows else rows[group])

def book_values(rule):return [canonical(cid)for cid in rule['custom_ids']]

def free_catalog():return {int(k):v for k,v in data()['free_by_class'].items()}

def selection_type(slot):
    if type(slot)is not int or slot not in SLOT_TYPES:raise ValueError('Unsupported custom selected slot')
    return SLOT_TYPES[slot]

def custom_type(custom_id):
    canonical(custom_id)
    if custom_id==0:return None
    if custom_id in FREE_EMOTES:return 24
    return custom_rules()[custom_id]['type']

def slot_value(slot,value):
    family=selection_type(slot)
    if value!=canonical(value.get('custom_id'),variant=value.get('variant'),ability=value.get('ability')) or (value['custom_id']==0 and family not in(1,7,15))or custom_type(value['custom_id'])not in(None,family):raise ValueError('Custom selected slot/family mismatch')
    return value

def free_ids(unit_class,slot=1):
    from els_server.domain.character_rules import CLASSES
    from els_server.domain.careers import PARENTS
    if unit_class not in CLASSES:raise ValueError('Custom career identity')
    family=selection_type(slot)
    if family==24:return set(FREE_EMOTES)
    if family==7:return {0}
    if family==15:return {0}
    rows=data()['free_customs']
    if family!=1:return {r['custom_id']for r in rows if r['type']==family and r['unit_class']==unit_class}
    values={0};current=unit_class
    for _ in range(CLASSES[unit_class]['stage']):
        current=PARENTS[current];values.update(r['custom_id']for r in rows if r['type']==1 and r['unit_class']==current)
    return values

def qualified(role,slot,value,owned):
    family=selection_type(slot)
    if value['custom_id']==0 and value['variant'] not in ((2,3)if role[0]==10 and family in(1,7)else(1,)):return False
    rows=owned.get(family,[])
    found=next((v for v in rows if v['custom_id']==value['custom_id']),None)
    return value==found if found else value['ability']==0 and value['custom_id']in free_ids(role[1],slot)

def admitted(s):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    return (s.client_build=='dx11_260923' and s.item_test and s.role=='game' and s.phase=='town_ready'
            and s.account.characters is not None and s.account.store is not None and current_lease(s))

def handle(s,event,sequence):
    if event.event_id==0x202 and event.kind==0x219:
        from els_server.protocol.character_custom_messages import socket_request
        from els_server.protocol.career_messages import use_ack
        from els_server.storage.character_custom import use_book,assign_ability,CustomUseError
        def validate_book():
            require_admitted(s)
            if (type(sequence)is not int or not 1<=sequence<2**32 or event.performers!=(0,)
                    or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
                raise ValueError('Custom book native town envelope')
        try:
            if s.account.characters is not None and s.account.store is not None:
                book=use_book(s.account.store.path,s.account.uid,s.account.account_id,event.payload,
                              s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence),validate=validate_book)
                if book is not None:return book['events']
            if socket_request(event.payload)is None:return None
            if (not admitted(s)or type(sequence)is not int or not 1<=sequence<2**32
                or event.performers!=(0,)or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Custom ability native town envelope')
            from els_server.domain.avatar_set_flow import context,validate
            captured=context(s)
            return assign_ability(s.account.store.path,s.account.uid,s.account.account_id,event.payload,s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence),validate=lambda:validate(s,captured))['events']
        except CustomUseError as error:return [use_ack(result=error.result)]
        except ValueError:return [use_ack(result=-1)]
    if event.kind==0x634:
        # Original CharInfo opener requests cash purchase availability, not
        # registered ownership, inventory books or an application permission.
        if (event.event_id!=0x202 or event.payload or not admitted(s)
            or type(sequence)is not int or not 1<=sequence<2**32 or event.performers!=(0,)
            or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):return []
        try:
            from els_server.domain.avatar_set_flow import context,validate
            from els_server.storage.character_custom import opening_info
            captured=context(s)
            return opening_info(s.account.store.path,s.account.uid,s.account.account_id,validate=lambda:validate(s,captured))
        except ValueError:return []
    if event.event_id!=0x202 or event.kind!=0x4cb:return None
    from els_server.protocol.character_custom_messages import acknowledgement
    if (not admitted(s) or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers!=(0,) or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
        return [acknowledgement(result=-1)]
    from els_server.storage.character_custom import select
    try:
        # Reuse the existing stable village/actor generation contract. This is
        # independent of avatar presets; no preset business action is invoked.
        from els_server.domain.avatar_set_flow import context,validate
        captured=context(s)
        return select(s.account.store.path,s.account.uid,s.account.account_id,event.payload,
                      s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence),validate=lambda:validate(s,captured))['events']
    except ValueError:return [acknowledgement(result=-1)]

def require_admitted(s):
    if not admitted(s):raise ValueError('Custom book requires current DX11 town game lease')

def restored(character):
    from els_server.protocol.character_custom_messages import selected_notice
    values=character.get('character_custom',{}).get('selected',{})
    if not values:return []
    return [selected_notice(character['uid'],character.get('title',0),values)]
