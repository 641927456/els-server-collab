"""Pinned owned consumable inputs; native effects/timers remain client-owned."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/consumable_extensions.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='12f8e2347f1544c0d93eff08c77dc1a6080789c6b90a92e19ecee2d8782d452c':raise ValueError('Consumable extension identity')
    data=json.loads(raw)
    if data['schema']!=1 or data['client_sha256']!=CLIENT_SHA or not data['owned_use_only'] or data['new_acquisition_sources']:raise ValueError('Consumable extension scope')
    out={}
    for kind,group,item_type in(('quick',6,5),('elixirs',4,7)):
        rows={}
        for row in data[kind]:
            item=client_data().item(row['template']);record=item['record']
            if (row['template']in rows or item['name']!=row['name'] or item['metadata']!=row['metadata'] or item['item_type']!=item_type
                or row['metadata']!=(0 if row.get('infinite',False)or row.get('singleton',False)else 2) or row['group']!=group or hashlib.sha256(record).hexdigest()!=row['record_sha256']
                or (0 if row.get('infinite',False)or row.get('singleton',False)else row['max_stack'])!=struct.unpack_from('<I',record,0x10)[0] or row['minimum_level']!=record[0xd1]):raise ValueError('Consumable original input changed')
            rows[row['template']]=row
        out[kind]=rows
    return out

def quick_templates():return frozenset(t for t,r in catalog()['quick'].items()if r.get('admitted',True))
def quick_bindings():return frozenset(r['binding']for t,r in catalog()['quick'].items()if t in quick_templates())
def inventory_definitions():return tuple(r for rows in catalog().values()for r in rows.values())
def ordinary(template):
    row=catalog()['quick'].get(template)
    if row is None:raise ValueError('Unsupported consumable extension')
    from els_server.domain.consumables import catalog as native_catalog
    from els_server.domain.quick_bindings import item_binding
    current=native_catalog()[template]
    if (current['effects']!=row['effects'] or current['cooldown_group']!=row['cooldown_group'] or current['cooldown_seconds']!=row['cooldown_seconds']
        or item_binding(template)!=row['binding']):raise ValueError('Consumable original effects changed')
    return current

def infinite(template):
    row=catalog()['quick'].get(template)
    return row is not None and row.get('infinite',False) is True

def elixir_templates():
    return tuple(t for t,r in catalog()['elixirs'].items()if r.get('admitted',True))
