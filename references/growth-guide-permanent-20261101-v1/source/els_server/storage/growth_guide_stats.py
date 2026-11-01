"""Task qualification from equipped and saved native adaptation sources."""
import collections,functools,hashlib,json,struct,time
from decimal import Decimal
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    p=PROJECT_ROOT/'els_server/data/growth_guide_stats.json';raw=p.read_bytes();d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=json.loads(p.with_suffix('.manifest.json').read_bytes())['payload_sha256'] or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=client_data().manifest['catalog_sha256']:
        raise ValueError('Guide adaptation source identity')
    return d

def adaptation(db,uid,character,items):
    from els_server.domain.character_stats import equipment_contributes
    from els_server.domain.ordinary_accessories import definitions as accessories
    from els_server.domain.tutorial_accessory import effective_style
    from els_server.storage.luciel_state import state,active_state
    from els_server.domain.item_expiration import expired
    from els_server.domain.equipment_requirements import class_matches
    from els_server.storage.growth_guide import avatar_catalog,exists
    c=client_data();d=catalog();selected=0;character=dict(character)
    if character['unit_type']==10:
        character.update(luciel_style=state(db,uid)['style'],luciel_active_unit=active_state(db,uid)['active_unit'])
        selected=effective_style(character)
    rows=[];ordinary=accessories();sets=collections.Counter();a=avatar_catalog();keys=[]
    from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
    for item in items:
        if item['group']!=9 or expired(item) or not equipment_contributes(item,character):continue
        t=item['template'];raw=c.item(t)['record']
        if not class_matches(character['unit_class'],raw[0xd3]):continue
        if t in ordinary and int(item['slot'] not in ordinary[t]['main_slots'])!=selected:continue
        if t in FASHION_EQUIP_SLOTS and character['unit_type']==10 and bool(raw[8]&4)!=bool(character['luciel_active_unit']):continue
        rows.append(item)
        definition=d['template_effects'].get(str(t))
        if definition:
            if hashlib.sha256(raw).hexdigest()!=definition['record_sha256']:raise ValueError('Guide adaptation native equipment')
            keys+=definition['options']
        for group,values in item.get('option_groups',{}).items():
            # These groups contain effect IDs. Chip/circuit grids contain
            # counters and coordinates and belong to their own native resolver.
            if group in ('0','1','9','10','11','12','13','14','15','16','17','18','19','20','21','25','26','29','31'):keys+=values
        set_id=struct.unpack_from('<I',raw,0x24)[0]
        if set_id in a['definitions'] and not a['definitions'][set_id].avatar_accessory:sets[set_id]+=1
    for set_id,count in sets.items():keys+=a['definitions'][set_id].effects(selector=0,count=count)
    # Avatar accessory effects require the saved Apply selection and original
    # admission/counting, including the native three-active-set limit.
    from els_server.storage.avatar_sets import snapshot
    from els_server.storage.avatar_current_equipment_2026 import snapshot_current
    from els_server.domain.avatar_equipped_counts_2026 import count_admitted
    from els_server.domain.avatar_accessory_effects_2026 import project_active_sets
    _,selection=snapshot(db,uid)
    if selection:
        side=character.get('luciel_active_unit',0)
        _,admitted=snapshot_current(db,owner=uid,side=side,category77=a['category77'],owner_7bd=False,policy=a['policy'],metadata=a['metadata'],now=int(time.time()))
        equipped=count_admitted(instances=admitted,selected=selection,context2912=0,side=side,membership=a['membership'],selector_overrides={},include_flag7=False)
        active,_=project_active_sets(records=selection,context2912=0,side=side,equipped=equipped,definitions=a['definitions'])
        for _,_,effects in active:keys+=effects
    if exists(db,'title_equipment'):
        from els_server.storage.titles import snapshot as title_state
        from els_server.domain.titles import definition
        title=title_state(db,uid,int(time.time()))['title']
        if title:keys+=[v for v in definition(title)['SOCKET_OPTION'].values() if v]
    value=sum((Decimal(str(d['options'].get(str(k),{}).get('m_fAdaptability',0)))*100 for k in keys),Decimal(0))
    if character.get('resonance',{}).get('enabled') and exists(db,'resonance2026_characters'):
        from els_server.domain.resonance_allocation_flow import definitions
        from els_server.storage.resonance_2026_pages import ResonancePages
        _,raw=definitions();account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()[0]
        saved=ResonancePages(db,raw).read(account,uid)
        if saved is not None and saved.enabled:value+=Decimal('0.07')*dict(saved.selected().points).get(22,0)
    from els_server.storage.town_rest_buffs import active as camp_buffs
    if camp_buffs(db,uid):value+=Decimal(2)
    return value
