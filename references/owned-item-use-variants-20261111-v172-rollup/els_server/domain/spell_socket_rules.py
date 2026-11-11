"""Native paid mystic writer with equivalent gift variants."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

DATA_SHA='e5940f00823f073b51a1196ecdfd29daf4a14e970313afed38a3fa871eb2ff1e'
TEMPLATES=frozenset((135877,135880,135883,135886,136109,136110,136111,136112))

GIFT_ALIASES = {
    711841: 135877,
    711843: 135879,
    711844: 135880,
    711846: 135882,
    711847: 135883,
    711849: 135885,
    711850: 135886,
    711852: 135888,
    711853: 135877,
    711855: 135879,
    711856: 135880,
    711858: 135882,
    711859: 135883,
    711861: 135885,
    711862: 135886,
    711864: 135888,
    711865: 135877,
    711867: 135879,
    711868: 135880,
    711870: 135882,
    711871: 135883,
    711873: 135885,
    711874: 135886,
    711876: 135888,
    711877: 135877,
    711879: 135879,
    711880: 135880,
    711882: 135882,
    711883: 135883,
    711885: 135885,
    711886: 135886,
    711888: 135888,
    717808: 136109,
    717809: 136110,
    717810: 136111,
    717811: 136112,
    720764: 136109,
    720765: 136110,
    720766: 136111,
    720767: 136112,
}
OWNED_ONLY_GIFTS = frozenset((711841, 711843, 711844, 711846, 711847, 711849, 711850, 711852, 711853, 711855, 711856, 711858, 711859, 711861, 711862, 711864, 711865, 711867, 711868, 711870, 711871, 711873, 711874, 711876, 711877, 711879, 711880, 711882, 711883, 711885, 711886, 711888))
GIFT_DATA_SHA = '9190f5040924890423ea36f04510c927523dbc36bcde5d00df1a351be8b6b081'

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

@functools.lru_cache(maxsize=1)
def gift_definitions():
    raw = (Path(__file__).resolve().parents[1] / 'data/gift_mystic_stones.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != GIFT_DATA_SHA:
        raise ValueError('Gift mystic source changed')
    data = json.loads(raw)
    rows = {int(key): row for key, row in data['items'].items()}
    if data['version'] != 1 or set(rows) != set(GIFT_ALIASES):
        raise ValueError('Gift mystic finite scope')
    for template, row in rows.items():
        item = client_data().item(template)
        base = material(GIFT_ALIASES[template])
        if (row['template'] != template or row['base_template'] != base['template']
                or (item['item_type'], item['metadata'], item['name']) != (7, row['metadata'], row['name'])
                or hashlib.sha256(item['record']).hexdigest() != row['record_sha256']
                or struct.unpack_from('<I', item['record'], 0x10)[0] != row['max_stack']
                or any(row[key] != base[key] for key in ('group', 'metadata', 'socket_group', 'color', 'pool_type'))):
            raise ValueError('Gift mystic original identity or pool')
    return rows

def material(template):
    if type(template) is int and template in GIFT_ALIASES:
        return gift_definitions()[template]
    from els_server.domain.shining_mystic_stones import TEMPLATES as shining,material as current_material
    if type(template)is int and template in shining:return current_material(template)
    row=catalog()['materials'].get(str(template))
    if row is None:raise ValueError('Unqualified mystic stone')
    return row

def draw(template,randbelow):
    template = GIFT_ALIASES.get(template, template)
    from els_server.domain.shining_mystic_stones import TEMPLATES as shining,draw as current_draw
    if type(template)is int and template in shining:return current_draw(template,randbelow)
    row=material(template);values=catalog()['pools'][str(row['pool_type'])];index=randbelow(len(values))
    if type(index)is not int or not 0<=index<len(values):raise ValueError('Mystic random bound')
    return values[index]

def validate_option(template,option):
    template = GIFT_ALIASES.get(template, template)
    from els_server.domain.shining_mystic_stones import TEMPLATES as shining,validate_option as current_validate
    if type(template)is int and template in shining:return current_validate(template,option)
    row=material(template)
    if type(option)is not int or option not in catalog()['pools'][str(row['pool_type'])]:raise ValueError('Mystic pending original pool')

def definitions():
    from els_server.domain.shining_mystic_stones import definitions as current_definitions
    return (*catalog()['materials'].values(), *current_definitions(), *gift_definitions().values())
