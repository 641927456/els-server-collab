"""Original equipment/set clear EXP options from actually admitted equipment."""
from functools import lru_cache
from decimal import Decimal
from pathlib import Path
import hashlib,json

EXP='m_fIncreaseDCBExpPercent'

@lru_cache(maxsize=1)
def catalog():
    from els_server.game_data import CLIENT_SHA,client_data
    from els_server.domain.title_option_data import catalog as options
    raw=(Path(__file__).resolve().parents[1]/'data/experience_equipment.json').read_bytes()
    d=json.loads(raw);data=client_data()
    if (hashlib.sha256(raw).hexdigest()!=SOURCE_SHA or d['schema']!=1
            or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=data.manifest['catalog_sha256']
            or d['new_acquisition_sources']is not False):raise ValueError('Equipment EXP source identity')
    source=options()
    for k,row in d['options'].items():
        if row!=source[int(k)]:raise ValueError('Equipment EXP option changed')
    with data.read_session():
        for k,row in {**d['innate'],**d['members']}.items():
            if hashlib.sha256(data.item(int(k))['record']).hexdigest()!=row['record_sha256']:
                raise ValueError('Equipment EXP template changed')
    return d

def contributes(item,character,now):
    from els_server.game_data import client_data
    from els_server.domain.character_stats import equipment_contributes
    from els_server.domain.equipment_requirements import class_matches
    from els_server.domain.item_expiration import expired
    from els_server.domain.ordinary_accessories import definitions,accepts_equipped
    from els_server.domain.tutorial_accessory import effective_style
    from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
    if item['group']!=9 or expired(item,now=now) or item.get('identified')is False:return False
    t=item['template'];raw=client_data().item(t)['record']
    if not equipment_contributes(item,character) or not class_matches(character['unit_class'],raw[0xd3]):return False
    if (int.from_bytes(raw[4:8],'little')>>12)&15==2 and raw[0xd2]!=character['unit_type']:return False
    side=effective_style(character)if character['unit_type']==10 else 0
    ordinary=definitions()
    if t in ordinary and (not accepts_equipped(item) or int(item['slot']not in ordinary[t]['main_slots'])!=side):return False
    if t in FASHION_EQUIP_SLOTS:
        if raw[0xd2]not in(0,character['unit_type']):return False
        if character['unit_type']==10 and bool(raw[8]&4)!=bool(character['luciel_active_unit']):return False
    return True

def bonus(db,owner,character,items,now):
    from els_server.game_data import client_data
    from els_server.domain.item_expiration import expired
    from els_server.storage.growth_guide import avatar_catalog
    from els_server.domain.avatar_current_selection_2026 import current_avatar_uids
    from els_server.domain.avatar_equipment_admission_2026 import EquipmentState,admit_current
    from els_server.domain.avatar_equipped_counts_2026 import count_admitted
    from els_server.domain.avatar_accessory_effects_2026 import project_active_sets,SetEffects
    from els_server.storage.avatar_sets import snapshot

    d=catalog();data=client_data();keys=[];counts={}
    worn=[i for i in items if i['group']==9 and not expired(i,now=now) and i.get('identified')is not False]
    # Native count insertion uses the first admitted template in sorted order.
    for item in sorted(worn,key=lambda i:i['template']):
        t=item['template'];raw=data.item(t)['record']
        if not contributes(item,character,now):continue
        innate=d['innate'].get(str(t))
        # Golden scarf/secret accessories retain their existing dedicated resolver.
        if innate and t not in range(980001,980017) and t not in range(118367,118372):keys+=innate['options']
        member=d['members'].get(str(t))
        if member:
            sid=member['set_id'];definition=d['sets'][str(sid)]
            if sid!=9520 and not definition['avatar_accessory'] and not raw[4]&128:
                selector,count=counts.get(sid,((int.from_bytes(raw[4:8],'little')>>20)&15,0))
                counts[sid]=(selector,count+1)
    for sid,(selector,count)in counts.items():
        row=d['sets'][str(sid)]
        definition=SetEffects(False,tuple(map(tuple,row['tiers'])),tuple(map(tuple,row['variants'])))
        keys+=definition.effects(selector=selector,count=count)
    _,selection=snapshot(db,owner)
    if selection:
        a=avatar_catalog();active_side=character.get('luciel_active_unit',0)
        selected=current_avatar_uids(items=worn,unit_type=character['unit_type'],unit_class=character['unit_class'],metadata=a['metadata'],admission_policy=a['policy'])
        states=tuple(EquipmentState(i['uid'],i['template'],i['group'],i['slot'],i['metadata'],i.get('durability',0),i.get('enhancement',0),a['category77'][i['template']],False)for i in worn if i['uid']in selected)
        admitted=admit_current(selected_uids=selected,equipment=states,class_id=character['unit_class'],side=active_side,policy=a['policy'])
        equipped=count_admitted(instances=admitted,selected=selection,context2912=0,side=active_side,membership=a['membership'],selector_overrides={},include_flag7=False)
        active,_=project_active_sets(records=selection,context2912=0,side=active_side,equipped=equipped,definitions=a['definitions'])
        for _,_,effects in active:keys+=effects
    # Caller admits ordinary PvE only. Secret-only options cannot leak here.
    return sum(int(Decimal(str(d['options'][str(k)][EXP]))*10000)for k in keys
               if str(k)in d['options'] and not d['options'][str(k)].get('DUNGEON_ONLY_TYPE'))

SOURCE_SHA='1daab85542d45adedc6b0040e5981f15a8be79c27b5b70ceaa52c2c2015d5893'
