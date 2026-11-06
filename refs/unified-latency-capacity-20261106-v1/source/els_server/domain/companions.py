"""Native pet/mount creation mappings for the pinned DX11 client."""
import functools,hashlib,json,re
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA

@functools.lru_cache(maxsize=1)
def catalog():
    data=json.loads((PROJECT_ROOT/'analysis/pet-mount-20261015/activation-catalog.json').read_text(encoding='utf8'))
    if data['client_sha256']!=CLIENT_SHA:raise ValueError('Companion client mismatch')
    for s in data['sources']:
        if hashlib.sha256((PROJECT_ROOT/s['path']).read_bytes()).hexdigest()!=s['sha256']:raise ValueError('Companion source changed')
    return {k:{int(t):v for t,v in data[k].items()} for k in ('pet','mount')}

def valid_name(name):
    # Native 2DABDA0/212EDE0: ASCII letters/digits and CJK; weighted limit 12.
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9\u3400-\u9fff]+',name) or sum(1 if ord(c)<128 else 2 for c in name)>12:
        raise ValueError('Invalid companion name')
    return name
