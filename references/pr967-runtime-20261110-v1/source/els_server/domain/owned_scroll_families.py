"""Exact existing scroll definitions; no grant sources or random rules."""
import functools,hashlib,json
from pathlib import Path

@functools.lru_cache(maxsize=1)
def catalog():
    from els_server.game_data import client_data
    path=Path(__file__).resolve().parents[1]/'data/owned_scroll_families.json'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='028fd5fb891bc88635b999f6fc2e79ad4f9170024d4ecd1a1131e6dba323fa73':raise ValueError('Owned scroll definition identity')
    data=json.loads(raw);client=client_data()
    if data['client_sha256']!=client.manifest['client_sha256'] or data['catalog_sha256']!=client.manifest['catalog_sha256']:raise ValueError('Owned scroll client identity')
    result={}
    for kind in ('enhancement','sage','restoration','resonance','reforge','challenge','identification','forget'):
        result[kind]={int(t):r for t,r in data[kind].items()}
        for t,row in result[kind].items():
            item=client.item(t)
            if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
                or item['item_type']!=7 or item['metadata']!=row['metadata']
                or (item['flags8']>>3)&31!=7 or row['group']!=4):raise ValueError('Owned scroll original record')
    return result

def register(metadata,groups,stacks):
    for rows in catalog().values():
        for t,r in rows.items():
            if t in metadata:
                if (metadata[t],groups[t])!=(r['metadata'],r['group']):raise ValueError('Existing scroll inventory classification conflict')
                continue
            metadata[t]=r['metadata'];groups[t]=r['group']
            stacks[t]=max(r['max_stack'],999) if r['max_stack']>1 else 1

def restoration_target(template,target):
    from els_server.game_data import client_data
    rule=catalog()['restoration'][template];original=client_data().item(target['template'])
    if not rule['minimum_level']<=original['record'][0xd1]<=rule['maximum_level']:raise ValueError('Restoration equipment level range')
    if rule['armor_only'] and original['equip_position'] not in (8,9,10,11):raise ValueError('Armor-only restoration scroll')
