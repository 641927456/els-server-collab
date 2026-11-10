"""Four current drop stones, original options with published KR probabilities.

Only supplements the existing native paid preview/apply writer. The eight
prior stones keep their approved distributions. No sources or option values.
"""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT

TEMPLATES=frozenset((135879,135882,135885,135888))
DATA_SHA='7afdfe1a5b4455b74f8a1382b9b776f3d1a012f40c275a4855697246a6e11458'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/shining_mystic_stones.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Shining mystic probability identity')
    data=json.loads(raw);native=client_data()
    if(data['version']!=1 or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=native.manifest['catalog_sha256']
       or data['weight_total']!=10000 or set(map(int,data['items']))!=TEMPLATES or set(data['items'])!=set(data['probabilities'])):
        raise ValueError('Shining mystic finite current scope')
    for source in data['native_sources']:
        if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Shining mystic original options changed')
    from els_server.domain.equipment_spell_rules import option_ids
    for key,row in data['items'].items():
        d=native.item(int(key));values=data['probabilities'][key]
        if(row['template']!=int(key)or d['item_type']!=7 or d['metadata']!=row['metadata']or row['group']!=4
           or row['socket_group']!=8+row['color']or row['color']not in(1,2,3,4)
           or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']or struct.unpack_from('<I',d['record'],0x10)[0]!=row['max_stack']):
            raise ValueError('Shining mystic original item identity')
        if(not values or len({v['option']for v in values})!=len(values)
           or any(type(v['option'])is not int or v['option']not in option_ids(row['socket_group'])
                  or type(v['weight'])is not int or not 0<v['weight']<=10000 for v in values)
           or sum(v['weight']for v in values)!=10000):raise ValueError('Shining mystic original option/weight bounds')
    return data

def material(template):
    if type(template)is not int or template not in TEMPLATES:raise ValueError('Unqualified shining mystic material')
    return catalog()['items'][str(template)]

def draw(template,randbelow):
    material(template);value=randbelow(10000)
    if type(value)is not int or not 0<=value<10000:raise ValueError('Shining mystic random bound')
    for row in catalog()['probabilities'][str(template)]:
        if value<row['weight']:return row['option']
        value-=row['weight']
    raise ValueError('Shining mystic probability total')

def validate_option(template,option):
    material(template)
    if type(option)is not int or option not in {v['option']for v in catalog()['probabilities'][str(template)]}:raise ValueError('Shining mystic pending option is outside published outcomes')

def definitions():return tuple(catalog()['items'].values())
