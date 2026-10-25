"""Eight existing-owned stones; exact native TYPE pools and approved weights."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

DATA_SHA='e5940f00823f073b51a1196ecdfd29daf4a14e970313afed38a3fa871eb2ff1e'
TEMPLATES=frozenset((135877,135880,135883,135886,136109,136110,136111,136112))

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/spell_socket.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Mystic fill source changed')
    data=json.loads(raw);native=client_data()
    if (data['version']!=1 or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=native.manifest['catalog_sha256']
        or data['fee_ed']!=200000 or set(map(int,data['materials']))!=TEMPLATES):raise ValueError('Mystic fill finite source')
    for key,row in data['materials'].items():
        item=native.item(int(key))
        if (row['template']!=int(key) or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or item['metadata']!=row['metadata'] or row['group']!=4 or row['socket_group']not in(9,10,11,12)
            or struct.unpack_from('<I',item['record'],0x10)[0]!=row['max_stack']):raise ValueError('Mystic stone original record')
        values=data['pools'][str(row['pool_type'])]
        from els_server.domain.equipment_spell_rules import option_ids
        if not values or values!=sorted(set(values))or any(type(v)is not int or v not in option_ids(row['socket_group'])for v in values):raise ValueError('Mystic stone exact color pool')
    return data

def material(template):
    row=catalog()['materials'].get(str(template))
    if row is None:raise ValueError('Unqualified mystic stone')
    return row

def draw(template,randbelow):
    row=material(template);values=catalog()['pools'][str(row['pool_type'])];index=randbelow(len(values))
    if type(index)is not int or not 0<=index<len(values):raise ValueError('Mystic random bound')
    return values[index]

def validate_option(template,option):
    row=material(template)
    if type(option)is not int or option not in catalog()['pools'][str(row['pool_type'])]:raise ValueError('Mystic pending original pool')

def definitions():return catalog()['materials'].values()
