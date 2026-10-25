"""Original 198B6E0 base capacity, including explicit zero Lua overrides.

Evidence recovered by the manufacture task, independently replayed for Sage.
This is not an instance expansion/wedge count.
"""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/native_socket_capacity.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='3c99c5752b1b81c470376c7c6229062de4a154eca34c3cdec1c4d9ad266c0d0e':
        raise ValueError('Native socket capacity source changed')
    c=json.loads(raw)
    if (c['schema_version']!=1 or c['client_sha256']!=CLIENT_SHA
        or c['catalog_sha256']!=client_data().manifest['catalog_sha256']
        or len(c['defaults'])!=2 or any(len(a)!=32 or any(len(b)!=16 for b in a) for a in c['defaults'])
        or len(c['custom'])!=3262 or sum(v==0 for v in c['custom'].values())!=2090
        or any(type(v) is not int or not 0<=v<=6 for a in c['defaults'] for b in a for v in b)
        or any(type(v) is not int or not 0<=v<=6 for v in c['custom'].values())):
        raise ValueError('Invalid native socket capacity catalog')
    return c


def capacity(template):
    d=client_data().item(template);c=catalog();key=str(template)
    # Membership is essential: a zero override forbids the generic fallback.
    if key in c['custom']:return c['custom'][key]
    return c['defaults'][int(bool(d['flags4']&1))][d['item_type']][(d['flags4']>>20)&15]
