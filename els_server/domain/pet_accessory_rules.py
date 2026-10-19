"""Local roll policy restricted to pinned native socket IDs and values."""
import functools,hashlib,json
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

def effects(equipment):
    result={}
    for e in equipment.values():
        r=rules()['options'].get(str(e['socket']))
        if r is None:raise ValueError('Unregistered pet equipment option')
        result[r['field']]=result.get(r['field'],0)+r['value']
    return result
