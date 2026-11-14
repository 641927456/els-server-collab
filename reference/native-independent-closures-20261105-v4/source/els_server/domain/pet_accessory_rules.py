"""Local roll policy restricted to pinned native socket IDs and values."""
import functools,hashlib,json,struct
from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

@functools.lru_cache(maxsize=1)
def rules():
    d=json.loads((PROJECT_ROOT/'analysis/pet-support-20261015/accessory-options.json').read_text(encoding='utf8'))
    s=d['source']
    if d['client_sha256']!=CLIENT_SHA or d['provenance']!='local_policy' or d['slots']!=2 or hashlib.sha256((PROJECT_ROOT/s['path']).read_bytes()).hexdigest()!=s['sha256']:raise ValueError('Pet accessory source/policy identity')
    from els_server.domain.pet_support import catalog
    if {int(i) for i in d['pools']}!=set(catalog()['equipment']):raise ValueError('Pet accessory pool coverage')
    for groups in d['pools'].values():
        if not groups or any(not group or any(str(i) not in d['options'] for i in group) for group in groups):raise ValueError('Pet accessory roll definition')
    return d

def roll(template,randbelow):
    groups=rules()['pools'].get(str(template))
    if not groups:raise ValueError('Unregistered pet equipment')
    def index(n):
        x=randbelow(n)
        if type(x) is not int or not 0<=x<n:raise ValueError('Invalid pet accessory random source')
        return x
    group=groups[index(len(groups))];return group[index(len(group))]


def supported(template):return str(template) in rules()['pools']


def validate(template,values):
    groups=rules()['pools'].get(str(template))
    if (groups is None or not isinstance(values,(list,tuple)) or len(values) not in (0,1)
            or any(type(v)is not int or not any(v in g for g in groups)for v in values)):
        raise ValueError('Invalid pet accessory identification')
    return list(values)


def initial_pending(item):
    return supported(item['template']) and 'identified'not in item and not item.get('option_groups',{}).get('1')


def socket(item):
    values=validate(item['template'],item.get('option_groups',{}).get('1',[]))
    if not item.get('identified',not initial_pending(item)) or len(values)!=1:
        raise ValueError('Identify the pet accessory before equipping it')
    return values[0]


def identification_fee(template):
    if not supported(template):raise ValueError('Unregistered pet accessory')
    from els_server.game_data import client_data
    # Original pending-item confirmation 2212D4B..2212D6E uses the raw price
    # at +1C, MULSS 0.05f, then CVTTSS2SI. All 18 pinned gems produce 50 ED.
    price=struct.unpack_from('<i',client_data().item(template)['record'],0x1c)[0]
    f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
    return int(f32(f32(price)*f32(0.05)))

def effects(equipment):
    result={}
    for e in equipment.values():
        r=rules()['options'].get(str(e['socket']))
        if r is None:raise ValueError('Unregistered pet equipment option')
        result[r['field']]=result.get(r['field'],0)+r['value']
    return result
