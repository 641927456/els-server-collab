"""Original finite reforge tables and explicitly labelled compatible outcomes."""
import functools,hashlib,json,secrets
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

DATA_SHA='834a71545f7f9dec5a5d0e252b570c0a70c4feb19816864b6fd29af4aff92f9f'
DEFAULT=[0,100,0]

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/equipment_reforge.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Reforge policy identity')
    c=json.loads(raw);data=client_data()
    if (c['schema_version']!=1 or c['policy_id']!='equipment-reforge-compatibility-v1' or c['client_sha256']!=CLIENT_SHA
        or c['catalog_sha256']!=data.manifest['catalog_sha256'] or c['source_resource_sha256']!='cd622db6fe266e6a28323c1eb0e16a565def39f7008c1e21858684b7548f4738'):raise ValueError('Reforge original client/resource identity')
    if len(c['targets'])!=369 or len(c['materials'])!=16 or len(c['restoration'])!=7 or len(c['options'])!=9:raise ValueError('Reforge finite scope')
    for row in [*c['targets'].values(),*c['materials'].values()]:
        if hashlib.sha256(data.item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Reforge original item record')
    if any(set(p)!=set(map(str,range(21))) for p in c['profiles'].values()):raise ValueError('Reforge cost levels')
    if any(set(p)!=set(map(str,range(1,22))) or any(r['SocketType'] not in (0,1) for r in p.values()) for p in c['stats'].values()):raise ValueError('Reforge fixed milestone levels')
    official=c.get('official_success_rates_by_class',{})
    if set(official)!={'1','2','3','4'}:raise ValueError('Scoped official reforge rate families')
    for table in official.values():
        if (table['denominator']!=10000 or set(table['thresholds'])!=set(map(str,range(21)))
            or any(type(n) is not int or not 0<n<10000 for n in table['thresholds'].values())):raise ValueError('Official reforge rate table')
    return c


def target(template):
    if type(template) is not int:return None
    row=catalog()['targets'].get(str(template))
    if row is None:return None
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    if (template not in definitions() or template not in VERIFIED_TEMPLATES or TEMPLATE_BAG_GROUPS.get(template)!=1 or TEMPLATE_MAX_STACKS.get(template)!=1):return None
    return row

def require_target(template):
    row=target(template)
    if row is None:raise ValueError('Reforge target is outside existing normal/template admission')
    return row

def profile(template,level):
    row=require_target(template)
    if type(level) is not int or not 0<=level<catalog()['max_level']:raise ValueError('Reforge level has no further attempt')
    return catalog()['profiles'][str(row['reforge_class'])][str(level)]

def state(template,values):
    require_target(template);c=catalog()
    if not isinstance(values,(list,tuple)) or len(values)!=3 or any(type(x) is not int for x in values):raise ValueError('Reforge state fields')
    level,life,failures=values
    if not 0<=level<=c['max_level'] or not 0<=life<=c['max_life']:raise ValueError('Reforge level/life bounds')
    limit=profile(template,level)['FixedUpCount'] if level<c['max_level'] else 0
    if not 0<=failures<=limit:raise ValueError('Reforge exact class/level failure threshold')
    return list(values)

def expected_options(template,level):
    row=require_target(template)
    if type(level) is not int or not 0<=level<=catalog()['max_level']:raise ValueError('Reforge option level')
    table=catalog()['stats'][str(row['reforge_class'])]
    return [table[str(n)]['SockectID'] if n<=level else 0 for n in range(3,22,3)]

def options(template,values):
    require_target(template)
    if not isinstance(values,(list,tuple)) or len(values)!=7 or any(type(x) is not int for x in values):raise ValueError('Reforge seven milestone positions')
    fully_unlocked=expected_options(template,catalog()['max_level'])
    if any(value not in (0,allowed) for value,allowed in zip(values,fully_unlocked)):raise ValueError('Reforge class-specific fixed option')
    return list(values)

def validate_instance(item):
    groups=item.get('option_groups',{});present='reforge' in item or '13' in groups
    if not present:return
    current=state(item['template'],item.get('reforge',DEFAULT))
    if groups.get('13')!=expected_options(item['template'],current[0]):raise ValueError('Reforge milestones do not match actual level')
    if item['count']!=1:raise ValueError('Reforged equipment cannot stack')

def guaranteed(template,current):
    current=state(template,current)
    return current[2]==profile(template,current[0])['FixedUpCount']

def demand(template,current,selected):
    p=profile(template,current[0]);choices={r['1']:r['2'] for r in p['SelectiveItem'].values()}
    full=guaranteed(template,current)
    if type(selected) is not int or (selected not in choices and not (full and selected==0)):raise ValueError('Reforge selected material')
    if full:return {},0
    result={selected:choices[selected]}
    for row in p['EssentialItem'].values():result[row['1']]=result.get(row['1'],0)+row['2']
    if any(str(t) not in catalog()['materials'] or type(n) is not int or n<1 for t,n in result.items()):raise ValueError('Reforge finite material demand')
    return result,p['Cost']


def profession_fee(cost,profession):
    """Original blacksmith percentages; compatible exact integer fee arithmetic."""
    if type(cost) is not int or cost<0 or not isinstance(profession,dict):raise ValueError('Reforge profession fee')
    if any(type(profession.get(k)) is not int for k in ('profession','level')):raise ValueError('Reforge profession state')
    from els_server.profession_data import profession_data
    percentages=dict(profession_data().registrations('SetDiscountPercentageReforgingFee'))
    if percentages!={level:level for level in range(1,11)}:raise ValueError('Reforge original profession percentages')
    percentage=percentages.get(profession['level'],0) if profession['profession']==2 else 0
    return cost*(100-percentage)//100

def advance(item,randbelow=secrets.randbelow):
    validate_instance(item);old=state(item['template'],item.get('reforge',DEFAULT));level,life,failures=old
    p=profile(item['template'],level)
    success=failures==p['FixedUpCount']
    if success:return state(item['template'],[level+1,life,0]),True
    if life<catalog()['life_per_attempt']:raise ValueError('Reforge life exhausted')
    if not success:
        # Use source-matched CN per-level rates for the four admitted families.
        # Keep the100-draw fallback defensive; every admitted family has a table.
        official=catalog()['official_success_rates_by_class'].get(str(p['SatReforgingEquipValue']))
        bound=official['denominator'] if official else 100
        threshold=official['thresholds'][str(level)] if official else catalog()['success_percent']
        roll=randbelow(bound)
        if type(roll) is not int or not 0<=roll<bound:raise ValueError('Reforge random bound')
        success=roll<threshold
    updated=state(item['template'],[level+int(success),life-catalog()['life_per_attempt'],0 if success else failures+1])
    return updated,success

def restore(item,material,quantity):
    validate_instance(item);old=state(item['template'],item.get('reforge',DEFAULT));level,life,failures=old
    gain=catalog()['restoration'].get(str(material))
    if (gain is None or type(quantity) is not int or quantity<1 or level==catalog()['max_level']
        or life==catalog()['max_life'] or quantity>(catalog()['max_life']-life+gain-1)//gain):raise ValueError('Reforge restore material/quantity/life')
    return state(item['template'],[level,min(catalog()['max_life'],life+gain*quantity),failures])

def cumulative_stats(template,level):
    row=require_target(template);state(template,[level,100,0]);table=catalog()['stats'][str(row['reforge_class'])]
    # Native6C1800 named setter stores HP/PA/MA/two reserved zeros/PD/MD.
    # This matches198E380 and the existing native seven-field stat layout.
    fields=('HpValue','PhysicAttValue','MagicAttValue',None,None,'PhysicDefValue','MagicDefValue')
    return [sum(table[str(n)].get(field,0) for n in range(1,level+1)) if field else 0 for field in fields]
