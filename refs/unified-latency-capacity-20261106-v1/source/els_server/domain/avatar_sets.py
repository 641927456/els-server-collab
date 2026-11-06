"""Owned current-template membership for native costume accessory Apply.

Only availability is checked here. Native 867440/198A0A0/70F980 compute the
first three qualifying sets and their effects; no server stat double count.
"""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA

SIDE_ONE=frozenset((1,3,5,7,9,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,36,38,40,42,55,56,57,58,59,60,61,62,63,64,65,66))

@functools.lru_cache(maxsize=1)
def catalog():
    m=json.loads((PROJECT_ROOT/'els_server/data/avatar_accessory_sets.manifest.json').read_text('utf-8'))
    raw=(PROJECT_ROOT/m['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=m['sha256']:raise ValueError('Avatar catalog SHA mismatch')
    d=json.loads(raw);sets=frozenset(d['sets']);items=dict(d['rows'])
    if d['schema']!=1 or d['client_sha256']!=CLIENT_SHA or len(sets)!=2071 or len(items)!=11176 or any(s not in sets for s in items.values()):
        raise ValueError('Avatar catalog identity/coverage')
    return sets,items

def available(items,side):
    if type(side) is not int or side not in (0,1):raise ValueError('Avatar side')
    from els_server.domain.item_expiration import expired
    _,membership=catalog();result=set()
    for item in items:
        if item['group']==9 and int(item['slot'] in SIDE_ONE)==side and not expired(item):
            set_id=membership.get(item['template'])
            if set_id:result.add(set_id)
    return result
