"""Native sealed-heater parts, shared points and role-at-opening rewards."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA

DATA_SHA='4e77e759cc1dc88656f780de2e5c6becf425d1fe55bab9747d65d9c83130ae47'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/modern_ice.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Modern ice catalog identity')
    data=json.loads(raw);client=client_data()
    if data['client_sha256']!=CLIENT_SHA or data['source_catalog_sha256']!=client.manifest['catalog_sha256']:raise ValueError('Modern ice client identity')
    witnesses={r['template']:r for r in data['native_readers']}
    for row in data['definitions']:
        item=client.item(row['template']);proof=witnesses[row['template']]
        if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or item['metadata']!=row['metadata']
            or(row['group'],row['max_stack'],proof['native_group'],proof['ok'],proof['consumed'])!=(4,99,4,1,304)
            or proof['record_sha256']!=row['record_sha256']):raise ValueError('Modern ice native item definition')
    data['machines']={int(k):v for k,v in data['machines'].items()}
    data['boxes']={int(k):v for k,v in data['boxes'].items()}
    return data

def machines():return catalog()['machines']
def boxes():return catalog()['boxes']

def entries():
    return tuple(dict(template=t,selection_count=0,modern_ice_box=True,
        entries=tuple(dict(template=output,quantity=1)for output in sorted(set(row['outputs'].values()))))for t,row in boxes().items())

def output_for(template,role,minor):
    if type(role)is not int or type(minor)is not int or minor not in(0,1)or(role!=10 and minor):raise ValueError('Ice cube opening role')
    output=boxes()[template]['outputs'].get(str(role)+':'+str(minor))
    if output is None:raise ValueError('Ice cube does not support this character')
    return dict(template=output,quantity=1)

def preview(template,character,flag):
    role=character['unit_type'];minor=character.get('luciel_active_unit',0)if role==10 else 0
    if flag!=minor:raise ValueError('Ice cube preview active character mismatch')
    return (output_for(template,role,minor),)

def rank(machine,template):
    row=machines()[machine]
    if template in row['boxes']:return 'S'
    from els_server.domain.shop_additions import catalog as common
    data=common('ice-common');profile=data['profiles'][data['machine_profiles'][str(row['paid'])]]
    ranks={catalog()['family_rank'][g['name']]for g in profile['groups']if any(e['template']==template for e in g['entries'])}
    if len(ranks)!=1:raise ValueError('Ice reward rank not established')
    return ranks.pop()

def points_earned(machine,template):
    if machine!=machines()[machine]['paid']:return 0
    return catalog()['point_per_rank'][rank(machine,template)]
