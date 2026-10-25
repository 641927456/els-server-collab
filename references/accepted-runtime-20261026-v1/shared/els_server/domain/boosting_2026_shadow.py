"""Selected2026 armor shadow-vector validation; no shadow rewards or random policy."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    p=Path(__file__).resolve().parents[1]/'data/boosting2026-shadow-options.json';raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='c2b68bd380a73b8369e0b4334dd44d137414e41527e94c6c20a450b4e2f37b79':raise ValueError('Selected shadow source changed')
    c=json.loads(raw)
    if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Selected shadow client mismatch')
    return c

def supported(template):
    return str(template) in catalog()['templates']

def validate(template,values):
    c=catalog();key=str(template)
    if key not in c['templates']:raise ValueError('Outside selected growth shadow scope')
    if hashlib.sha256(client_data().item(template)['record']).hexdigest()!=c['target_records'][key]:raise ValueError('Selected shadow target changed')
    if not isinstance(values,(list,tuple)) or len(values)!=3 or any(type(v) is not int or v not in c['templates'][key][i] for i,v in enumerate(values)):raise ValueError('Invalid selected shadow slots')
    return list(values)

def require_identified(item):
    if supported(item['template']):validate(item['template'],item.get('option_groups',{}).get('25',[]))
