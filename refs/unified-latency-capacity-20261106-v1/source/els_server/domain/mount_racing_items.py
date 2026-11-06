"""Current native crystal/material inventory records; no grant source here."""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

@functools.lru_cache(maxsize=1)
def definitions():
    data=json.loads((PROJECT_ROOT/'els_server/data/mount_racing_items.json').read_bytes())
    if data['client_sha256']!=CLIENT_SHA or [r['template']for r in data['items']]!=[714108,714109,714118]:
        raise ValueError('Mount racing item source')
    for row in data['items']:
        item=client_data().item(row['template'])
        if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or (item['metadata'],item['item_type'],struct.unpack_from('<I',item['record'],16)[0])
               !=(row['metadata'],row['item_type'],row['max_stack'])
            or row['group']!=(3 if row['template']==714109 else 4)):
            raise ValueError('Mount racing item record mismatch')
    return data['items']
