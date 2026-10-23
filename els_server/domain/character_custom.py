"""Existing-source permanent Elsword motions/emotes and finite non-LuCiel faces.

The client owns the UI, motion, model and effect behavior. This module admits
only primary book IDs in the reviewed current qualified local ED catalog.
"""
import functools,json
from pathlib import Path

DATE1='2001-01-01 00:00:00'
DATE2='2050-01-01 00:00:00'
SLOT_TYPES={1:1,2:2,7:7,8:7,13:7,14:7,24:24,25:24,26:24,27:24}
FACE_UNITS=frozenset({1,2,3,4,5,6,7,8,9,11,12,13,14,15})
COUNTS={1:52,2:321,7:85,24:71}
FREE_EMOTES=frozenset({17000,17033,17034,17035,17036})

@functools.lru_cache(maxsize=1)
def catalog():
    data=json.loads((Path(__file__).parents[1]/'data/character_custom_permanent.json').read_text(encoding='utf8'))
    if (data['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709' or len(data['books'])!=529
        or data['free_emote_ids']!=sorted(FREE_EMOTES)):
        raise ValueError('Permanent custom catalog identity')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    rules={}
    for r in data['books']:
        if (type(r['book']) is not int or type(r['custom_id']) is not int or r['book'] in rules
            or r['type'] not in COUNTS or r['slot']!=r['type']
            or r['unit_type'] not in (FACE_UNITS if r['type']==2 else {1})
            or r['book'] not in VERIFIED_TEMPLATES or TEMPLATE_BAG_GROUPS[r['book']]!=4):
            raise ValueError('Permanent custom catalog qualification')
        rules[r['book']]=r
    if (len({r['custom_id'] for r in rules.values()})!=529
        or {t:sum(r['type']==t for r in rules.values())for t in COUNTS}!=COUNTS
        or {0,*FREE_EMOTES,*free_catalog().values()}&{r['custom_id']for r in rules.values()}):raise ValueError('Permanent custom ID ambiguity')
    return rules

def canonical(custom_id):
    if type(custom_id) is not int or custom_id not in ({0}|FREE_EMOTES|set(free_catalog().values())|{r['custom_id'] for r in catalog().values()}):
        raise ValueError('Unqualified permanent custom ID')
    return dict(custom_id=custom_id,ability=0,date1=DATE1,date2=DATE2,variant=1)

@functools.lru_cache(maxsize=1)
def free_catalog():
    data=json.loads((Path(__file__).parents[1]/'data/character_custom_permanent.json').read_text(encoding='utf8'))
    values={int(k):v for k,v in data['free_by_class'].items()}
    from els_server.domain.character_rules import CLASSES
    if len(values)!=13 or len(set(values.values()))!=13 or any(CLASSES[k]['base_class']!=1 or type(v) is not int for k,v in values.items()):
        raise ValueError('Elsword free-motion source qualification')
    return values

def selection_type(slot):
    if type(slot) is not int or slot not in SLOT_TYPES:raise ValueError('Unsupported custom selected slot')
    return SLOT_TYPES[slot]

def custom_type(custom_id):
    canonical(custom_id)
    if custom_id==0:return None
    if custom_id in FREE_EMOTES:return 24
    if custom_id in free_catalog().values():return 1
    return next(r['type']for r in catalog().values()if r['custom_id']==custom_id)

def slot_value(slot,value):
    family=selection_type(slot)
    if value!=canonical(value.get('custom_id')) or (value['custom_id']==0 and family in (2,24)) or custom_type(value['custom_id']) not in (None,family):
        raise ValueError('Custom selected slot/family mismatch')
    return value

def free_ids(unit_class,slot=1):
    # Current11F2CB0/UI suppresses this career's own free row; ID0 is the
    # native current-career default. Prior career free motions remain selectable.
    from els_server.domain.careers import PARENTS
    from els_server.domain.character_rules import CLASSES
    if slot==2:return set()  # No face free/default producer admitted.
    if unit_class not in free_catalog():raise ValueError('Elsword custom career identity')
    family=selection_type(slot)
    if family==7:return {0}
    if family==24:return set(FREE_EMOTES)
    values={0};seen=set();current=unit_class
    for _ in range(CLASSES[unit_class]['stage']):
        if current in seen:raise ValueError('Custom career ancestry cycle')
        seen.add(current);current=PARENTS[current];values.add(free_catalog()[current])
    return values

def admitted(s):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    return (s.client_build=='dx11_260923' and s.item_test and s.role=='game' and s.phase=='town_ready'
            and s.account.characters is not None and s.account.store is not None and current_lease(s))

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x4cb:return None
    from els_server.protocol.character_custom_messages import acknowledgement
    if (not admitted(s) or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
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
