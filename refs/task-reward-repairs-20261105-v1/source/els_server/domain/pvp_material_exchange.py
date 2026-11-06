"""Original Camilla coin -> selected specialization stone recipes."""
from functools import lru_cache
import hashlib,json,struct
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='af4a0ec213706f475231f27871006ba212de6903f6b25d445ef6b15a8e33d6f3'

@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/pvp_material_exchange.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('PvP material original data identity')
    data=json.loads(raw);c=client_data()
    if data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=c.manifest['catalog_sha256']:raise ValueError('PvP material client identity')
    for row in data['definitions']:
        item=c.item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or(item['metadata'],item['item_type'],row['group'],row['native_ok'],row['native_consumed'])!=(2,6,3,1,304)or struct.unpack_from('<I',item['record'],16)[0]!=row['max_stack']:raise ValueError('PvP stone native reader')
    for row in data['recipes']:
        a=row['arguments']
        if row['function']!='g_pItemManager.AddItemExchangeData'or a[1:4]!=[40016,3,72920]or a[4]not in(72930,72940,72950)or a[5]!=1 or a[7]!={'m_iServerGroupID':-1,'m_iSourceQuantity':1}:raise ValueError('PvP original selected exchange')
    return data

def recipe(r,town):
    if(town not in map(int,catalog()['towns'])or r.house!=40016 or r.source!=72920 or r.source_uid!=0 or r.source_quantity!=1 or r.exchange_type!=3 or r.native_flag!=1 or r.native_index!=0 or not 1<=r.quantity<=1000):raise ValueError('PvP material current NPC selection')
    matches=[row for row in catalog()['recipes']if row['arguments'][4]==r.destination]
    if len(matches)!=1:raise ValueError('PvP specialization stone selection')
    return matches[0]
