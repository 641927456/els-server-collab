"""Current native studio backgrounds and the supported ordinary quest source."""
from pathlib import Path
import functools,hashlib,json,struct
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    directory=Path(__file__).resolve().parents[1]/'data'
    raw=(directory/'photo_zone.json').read_bytes()
    manifest=json.loads((directory/'photo_zone.manifest.json').read_bytes())
    data=json.loads(raw)
    if(data['client_sha256']!=CLIENT_SHA or manifest['client_sha256']!=CLIENT_SHA
            or hashlib.sha256(raw).hexdigest()!=manifest['sha256']):
        raise ValueError('Studio native catalog identity')
    for key,row in data['items'].items():
        item=client_data().item(int(key))
        if(hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
                or item['metadata']!=row['metadata']or item['item_type']!=row['item_type']):
            raise ValueError('Studio item definition changed')
    return data

def quests():return catalog()['quests']
def subquests():return catalog()['subquests']

@functools.lru_cache(maxsize=1)
def ticket_definition():
    path=Path(__file__).resolve().parents[1]/'data/photo_zone_ticket.json'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='47887c5f82178dc852b2bc044ce31110fd8fac10ebea6cb073f60b6c52613365':
        raise ValueError('Studio ticket native proof identity')
    row=json.loads(raw);item=client_data().item(row['template'])
    from els_server.domain.activity_2026_stack_policy import effective_stack
    if(row['client_sha256']!=CLIENT_SHA or(row['template'],row['metadata'],row['group'])!=(288494,2,4)
            or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or struct.unpack_from('<I',item['record'],0x10)[0]!=row['source_max_stack']
            or row['max_stack']!=effective_stack(row['source_max_stack'])
            or row['native']!={'passed':True,'item_reader':'D9A550','consumed':304,'bag_classifier':'19803A0'}):
        raise ValueError('Studio ticket original definition')
    return row
