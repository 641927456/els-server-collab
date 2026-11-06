"""Original enhancement materials admitted by pinned native body/classification."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA


@functools.lru_cache(maxsize=1)
def definitions():
    raw=(PROJECT_ROOT/'els_server/data/equipment_ui_materials.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='1105b44ebbc9342f057be0f03e65fdc7aaa6e00870b42e9cb1bbb80b3b2c1e16':
        raise ValueError('Equipment material evidence changed')
    data=json.loads(raw);proof=(PROJECT_ROOT/data['native_proof']).read_bytes()
    if data['client_sha256']!=CLIENT_SHA or data['source_catalog_sha256']!=client_data().manifest['catalog_sha256'] or hashlib.sha256(proof).hexdigest()!=data['native_proof_sha256']:
        raise ValueError('Equipment material provenance')
    result={}
    for row in data['items']:
        d=client_data().item(row['template'])
        if hashlib.sha256(d['record']).hexdigest()!=row['record_sha256'] or (d['item_type'],d['metadata'],row['group'])!=(7,2,4):
            raise ValueError('Equipment material definition changed')
        result[row['template']]=row
    if set(result)!={163135,163284}:raise ValueError('Equipment material coverage')
    return result
