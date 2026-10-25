"""Finite original engraving pools and explicitly compatible paid preview policy."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='4e1847711eb0c3e5fe18097d12231748f810b1b5ec55a8a4546bbc64c941b664'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/equipment_engrave.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Engraving policy identity')
    c=json.loads(raw);data=client_data()
    if (c['schema_version']!=1 or c['policy_id']!='equipment-engrave-compatibility-v1' or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=data.manifest['catalog_sha256'] or c['source_resource_sha256']!='0be870c1b06b189e55286232a03e3dc11134834cbd05de1f571a5380cf67ceb6'):raise ValueError('Engraving original source identity')
    if len(c['targets'])!=165 or set(map(int,c['materials']))!=set(range(136040,136049)) or [len(c['options'][str(i)]) for i in range(3)]!=[86,32,210]:raise ValueError('Engraving finite scope')
    if c['fees']!={'1':1600000,'2':240000,'3':24000}:raise ValueError('Engraving original fees')
    for row in [*c['targets'].values(),*c['materials'].values()]:
        if hashlib.sha256(data.item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Engraving original item record')
    for template,row in c['materials'].items():
        pool=c['pools'][template]
        if (row['metadata'],row['group'],row['max_stack'])!=(2,4,300) or row['component']!=(int(template)-136040)//3 or not pool or len(pool)!=len(set(pool)):raise ValueError('Engraving material pool')
        if any(c['options'][str(row['component'])].get(str(v),{}).get('m_iIconItemId')!=int(template) for v in pool):raise ValueError('Engraving exact icon pool')
    return c

def target(template):
    if type(template) is not int:return None
    row=catalog()['targets'].get(str(template))
    if row is None:return None
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    return row if template in definitions() and template in VERIFIED_TEMPLATES and TEMPLATE_BAG_GROUPS.get(template)==1 and TEMPLATE_MAX_STACKS.get(template)==1 else None

def require_line(template,line,component):
    row=target(template)
    if row is None or type(line) is not int or not 0<=line<row['slots'] or type(component) is not int or not 0<=component<3:raise ValueError('Engraving current target line/component')

def options(template,group,values):
    if type(group) is not int:raise ValueError('Engraving group type')
    require_line(template,group-14,0)
    if not isinstance(values,(list,tuple)) or len(values)!=3 or any(type(v) is not int for v in values):raise ValueError('Engraving exact three-component line')
    if any(v!=0 and str(v) not in catalog()['options'][str(i)] for i,v in enumerate(values)):raise ValueError('Engraving unknown component ID')
    return list(values)

def material(template,component):
    row=catalog()['materials'].get(str(template)) if type(template) is int else None
    if row is None or row['component']!=component:raise ValueError('Engraving finite component material')
    return row

def candidate(template,component,value):
    material(template,component)
    if type(value) is not int or value not in catalog()['pools'][str(template)]:raise ValueError('Engraving original material candidate pool')
    return value

def generate(template,component,randbelow):
    row=material(template,component);pool=catalog()['pools'][str(template)];draw=randbelow(len(pool))
    if type(draw) is not int or not 0<=draw<len(pool):raise ValueError('Engraving random bound')
    return pool[draw],catalog()['fees'][str(row['grade'])]
