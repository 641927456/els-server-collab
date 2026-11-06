"""Unchanged owned retained inventory readers, without item producers or use."""
from pathlib import Path
from types import MappingProxyType
import functools,hashlib,json,struct

DATA_SHA='a0d28e566c439c655d426d33988df14cf3fe845f969edaa37e9a06c6ed5122dc'
TEMPLATES=frozenset((118707, 118709, 118713, 118714, 295995, 313132, 701005, 701006, 701007, 701009, 701011, 716611, 718783, 720017, 720835, 723610, 723618, 10078925, 10078926, 10078927, 10078928, 10078929, 10130467, 60001529, 60004275, 60008002, 80000087, 80000373, 80000599, 80001350, 80001371, 80001390, 80001452, 80001596, 80001890, 80001891, 80001892, 85000526, 85000527, 85001866, 85001867, 85001960, 85003046, 90000739, 90001710, 100000168, 100001054, 210000120, 250002820, 250002821))

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data,CLIENT_SHA
    p=Path(__file__).resolve().parents[1]/'data/retained_native_consumables.json'
    raw=p.read_bytes();data=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['schema_version']!=1
        or data['client_sha256']!=CLIENT_SHA or data['new_sources']or data['consumption_enabled']
        or set(r['template']for r in data['items'])!=TEMPLATES or len(data['items'])!=len(TEMPLATES)):
        raise ValueError('Retained native consumable reader contract')
    rows={}
    for r in data['items']:
        item=client_data().item(r['template']);record=item['record']
        if (hashlib.sha256(record).hexdigest()!=r['record_sha256']or item['name']!=r['name']
            or item['metadata']!=r['metadata']or item['item_type']!=r['item_type']
            or (r['item_type'],r['metadata'],r['group'])not in((5,2,6),(7,2,4),(7,0,4),(3,0,27))
            or struct.unpack_from('<I',record,0x10)[0]!=r['raw_max_stack']
            or r['owned_max_stack']!=(1 if r['raw_max_stack']<=1 else max(r['raw_max_stack'],999))or record[0xd1]!=r['minimum_level']):
            raise ValueError('Retained native item definition changed')
        rows[r['template']]=MappingProxyType(r)
    return MappingProxyType(rows)

class _ExistingNativeConsumable(dict):
    __slots__=('_original',)

def read_existing(item):
    keys={'uid','template','metadata','count','group','slot'}
    r=definitions().get(item.get('template'))if type(item)is dict else None
    if (r is None or set(item)-{'expires_at','lock_until','sealed','seal_used'}!=keys
        or any(type(item[k])is not int for k in keys)or not 0<item['uid']<2**63
        or (item['metadata'],item['group'])!=(r['metadata'],r['group'])
        or not 0<item['count']<=r['owned_max_stack']):
        raise ValueError('Retained native owned inventory shape')
    from els_server.domain.bag_capacity import wire_limit
    if not 0<=item['slot']<wire_limit(r['group']):raise ValueError('Retained native inventory slot')
    value=dict(item)
    if 'expires_at'in value:
        from els_server.domain.item_expiration import validate
        validate(value['expires_at'])
    if 'lock_until'in value:
        from els_server.domain.item_locks import validate
        validate(value['lock_until'])
    if 'sealed'in value or 'seal_used'in value:
        from els_server.storage.item_seals import validate
        validate(value.get('sealed',False),value.get('seal_used',0))
    out=_ExistingNativeConsumable(value);out._original=dict(value)
    return out

def validate_existing(item):
    if type(item)is not _ExistingNativeConsumable or dict(item)!=item._original:
        raise ValueError('Unchanged owned native consumable reader required')
    read_existing(dict(item))
    return item
