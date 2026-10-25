"""Existing-owned Golden accessories' exact clear-only economic effects.

Combat stats, resistance, HP, triggers and timers remain native. No item
source or wear permission is added. Rounding reuses the existing local
reward compatibility policy; it is not a complete retail economy formula.
"""
import functools,hashlib,json,math,time
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.character_stats import f32


@functools.lru_cache(maxsize=1)
def catalog():
    manifest=json.loads((PROJECT_ROOT/'els_server/data/equipment_economy.manifest.json').read_text('utf8'))
    raw=(PROJECT_ROOT/manifest['path']).read_bytes();data=json.loads(raw);client=client_data()
    if (manifest['schema']!=1 or data['schema']!=1 or hashlib.sha256(raw).hexdigest()!=manifest['sha256']
        or manifest['client_sha256']!=data['client_sha256'] or data['client_sha256']!=CLIENT_SHA
        or data['source_catalog_sha256']!=client.manifest['catalog_sha256']
        or data['new_acquisition_sources'] is not False or data['set_id']!=9520):raise ValueError('Equipment economy source identity')
    from els_server.domain.title_option_data import catalog as option_catalog
    from els_server.domain.ordinary_accessories import definitions
    expected=set(range(118367,118372))|set(range(980001,980017))
    if set(map(int,data['items']))!=expected:raise ValueError('Equipment economy template scope')
    for key,row in data['items'].items():
        template=int(key);record=client.item(template)['record'];rule=definitions().get(template)
        if (hashlib.sha256(record).hexdigest()!=row['record_sha256'] or not rule or rule['restricted']
            or int.from_bytes(record[0x24:0x28],'little')!=row['set_id']):raise ValueError('Equipment economy template changed')
    if set(data['effects'])!={'200162','200165','200166','60907'} or data['tiers']!=[[3,200165],[4,200165],[4,200162],[5,200165],[5,200162],[5,200166]]:
        raise ValueError('Equipment economy set/effect scope')
    for key,row in data['effects'].items():
        if row!=option_catalog()[int(key)]:raise ValueError('Equipment economy option changed')
    return data


def resolve(db,uid,source,dungeon_type,*,now=None):
    result=dict(items=[],set_id=9520,set_count=0,set_options=[],ed_rate=0.,experience_rate=0.)
    # Native condition is clear reward, never ground-coin pickup, quest or shop.
    if source!='clear':return result
    if db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('inventory_items','characters')").fetchone()[0]!=2:return result
    row=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(uid,)).fetchone()
    if row is None:return result
    character=dict(unit_type=row[0],unit_class=row[1],level=row[2])
    data=client_data()
    if data.unit(row[1])['unitType']!=row[0]:raise ValueError('Equipment economy character identity')
    selected=0
    if row[0]==10:
        from els_server.storage.luciel_state import state,active_state
        character.update(luciel_style=state(db,uid)['style'],luciel_active_unit=active_state(db,uid)['active_unit'])
        from els_server.domain.tutorial_accessory import effective_style
        selected=effective_style(character)
    from els_server.storage.inventory_state import load_items
    from els_server.domain.ordinary_accessories import definitions,accepts_equipped
    from els_server.domain.equipment_requirements import class_matches
    from els_server.domain.item_expiration import expired
    source_data=catalog();rules=definitions();clock=int(time.time()) if now is None else now
    keys=[]
    for item in load_items(db,uid):
        template=item['template'];entry=source_data['items'].get(str(template))
        if entry is None or not accepts_equipped(item) or expired(item,now=clock):continue
        rule=rules[template];minor=item['slot'] not in rule['main_slots']
        if int(minor)!=selected or rule['companion_only'] and row[0]!=10:continue
        record=data.item(template)['record']
        if not class_matches(row[1],record[0xd3]):continue
        # Locked/sealed retained instances are not stripped of their existing
        # effects here. New equip permission remains the wear transaction's job.
        active=[i for i in entry['options'] if (i==60907 and dungeon_type!=3) or (i!=60907 and dungeon_type==3)]
        if not active:continue
        keys.extend(active);result['items'].append(dict(uid=item['uid'],template=template,options=active))
        if entry['set_id']==9520:result['set_count']+=1
    if dungeon_type==3:
        eligible=[required for required,_ in source_data['tiers'] if required<=result['set_count']]
        if eligible:
            highest=max(eligible)
            result['set_options']=[i for required,i in source_data['tiers'] if required==highest]
            keys.extend(result['set_options'])
    # Compose exact source percentages before the existing float32 reward
    # product/truncation. Repeated float32 additions would turn 1+1+1+2%
    # into 4.9999997% and underpay a120ED clear. This percentage composition
    # is explicit local compatibility, not a replacement native stat sum.
    result['ed_rate']=f32(math.fsum(source_data['effects'][str(k)].get('m_fIncreaseEDPercent',0) for k in keys))
    result['experience_rate']=f32(math.fsum(source_data['effects'][str(k)].get('m_fIncreaseDCBExpPercent',0) for k in keys))
    result['rate_composition']='source_sum_then_f32_local_compatibility'
    return result
