"""Original fused elixir choices, consumed by the shared inventory-box writer."""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import CLIENT_SHA,client_data

DATA_SHA='9da37eecc3f78b6a41d7248beea68f65cc184d8e81af27a7b5dbe43c40a0ea56'


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/fusion_elixir_cubes.json').read_bytes()
    data=json.loads(raw);client=client_data()
    if (hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['client_sha256']!=CLIENT_SHA
        or data['catalog_sha256']!=client.manifest['catalog_sha256']):
        raise ValueError('Fused elixir box source identity')
    proof=data['native'];native={r['template']:r for r in proof['rows']}
    if proof['all_passed']is not True or proof['live_process_access']is not False:
        raise ValueError('Fused elixir native reader evidence')
    for row in (*data['boxes'],*data['outputs']):
        item=client.item(row['template']);p=native[row['template']]
        if ((item['name'],item['metadata'])!=(row['name'],row['metadata'])
            or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or row['record_sha256']!=p['record_sha256'] or row['group']!=p['native_group'] or row['group']!=4
            or row['max_stack']!=struct.unpack_from('<I',item['record'],16)[0]
            or [(c['count'],c['ok'],c['consumed'],c['template'],c['metadata'])for c in p['cases']]
                !=[(n,1,304,row['template'],row['metadata'])for n in(1,row['max_stack'])]):
            raise ValueError('Fused elixir native item identity')
    result={}
    for row in data['boxes']:
        rule=row['random_rule'];t=row['template']
        if (rule['m_ItemID'],rule['m_iGiveCount'],rule['m_UseCondition'],rule['m_KeyItemID'],rule['m_RequiredKeyCount'])!=(t,1,1,0,0):
            raise ValueError('Fused elixir original choice mode')
        result[t]=MappingProxyType(row)
    return MappingProxyType(result)
