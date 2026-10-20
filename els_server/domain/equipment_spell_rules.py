"""Finite original mystic-socket identities; no RNG or client stat formulas."""
import functools
import hashlib
import json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

DATA_SHA='404c9151ca94106e38c611825fa89d2c4f11e6900fd2b52da33e49af17f4ce7c'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/equipment_spell.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Mystic socket source identity')
    c=json.loads(raw)
    if (c['schema_version']!=1 or c['client_sha256']!=CLIENT_SHA
            or c['catalog_sha256']!=client_data().manifest['catalog_sha256']
            or len(c['targets'])!=1178 or sum(map(len,c['options'].values()))!=2364
            or set(c['options'])!={'9','10','11','12'} or len(c['exchange_targets'])!=122):
        raise ValueError('Mystic socket finite source scope')
    for t,row in c['targets'].items():
        d=client_data().item(int(t))
        if ((d['item_type'],d['metadata'],d['equip_position'])!=(1,1,2)
                or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']):
            raise ValueError('Mystic weapon original record')
    return c

@functools.lru_cache(maxsize=4)
def option_ids(group):
    return frozenset(catalog()['options'][str(group)])

def ticket_definitions():
    """Bounded one-ticket instance compatibility; native stack maximum unknown.

    This registers neither a shop/reward nor other ticket variants. A single
    count1 instance uses the already supported type7/metadata0 inventory DTO.
    """
    row=next(r for r in catalog()['tickets'] if r['template']==136058)
    d=client_data().item(136058)
    if (d['item_type'],d['metadata'])!=(7,0) or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']:
        raise ValueError('Plain red transfer ticket original identity')
    return [dict(template=136058,metadata=0,group=4,max_stack=1)]

def options(template,group,values):
    """Stored vectors retain dormant slots after an enhancement downgrade."""
    key=str(group);c=catalog()
    if (str(template) not in c['targets'] or key not in c['storage_capacity']
            or not isinstance(values,(list,tuple)) or len(values)>c['storage_capacity'][key]
            or any(type(v) is not int or v!=0 and v not in option_ids(int(key)) for v in values)):
        raise ValueError('Original mystic weapon/color option vector required')
    return list(values)

def capacity(item,group):
    c=catalog();row=c['targets'].get(str(item['template']))
    if row is None or str(group) not in c['storage_capacity']:raise ValueError('Mystic weapon/color required')
    enhancement=item.get('enhancement',0)
    if type(enhancement) is not int or enhancement<0:raise ValueError('Broken mystic weapon')
    expanded=row['tag64'] or row['tag56'] and enhancement>=9
    return (3 if expanded else 1) if int(group)==12 else (9 if expanded else 5)

def exchange_target(item):
    c=catalog()
    if (item['template'] not in c['exchange_targets'] or item['group']!=1 or item['count']!=1
            or item.get('enhancement',0)<9 or item.get('identified') is False or item.get('sealed')):
        raise ValueError('Owned identified unequipped +9 raid weapon required')
    if capacity(item,9)!=9 or capacity(item,12)!=3:raise ValueError('Expanded native transfer slots required')

def exchange(left,right,group,index):
    """Current CN transfer: swap whole colored columns or one giant slot."""
    exchange_target(left);exchange_target(right)
    if left['uid']==right['uid']:raise ValueError('Two different owned weapon instances required')
    if type(group) is not int or group not in (9,10,11,12) or type(index) is not int:
        raise ValueError('Mystic exchange color/index')
    if group!=12 and index!=-1 or group==12 and not 0<=index<3:
        raise ValueError('Color column or exact giant slot required')
    previous_left=left.get('option_groups',{});previous_right=right.get('option_groups',{})
    n=9 if group!=12 else 3
    a=options(left['template'],group,previous_left.get(str(group),[]));a+= [0]*(n-len(a))
    b=options(right['template'],group,previous_right.get(str(group),[]));b+= [0]*(n-len(b))
    if group==12:
        if not a[index] and not b[index]:raise ValueError('Neither selected giant slot has an installed option')
        a[index],b[index]=b[index],a[index]
    else:
        if not any(a) and not any(b):raise ValueError('Neither column has an installed option')
        a,b=b,a
    return ({**previous_left,str(group):a},{**previous_right,str(group):b})
