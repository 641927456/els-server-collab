"""Four source-owned permanent pet items; no activation or pet simulation."""
from pathlib import Path
import functools,hashlib,json,struct
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.companions import catalog as companion_catalog
DATA=Path(__file__).resolve().parents[1]/'data/ep_pets.json'
SHA='8ada2750184a372a9fb644a71c378dac9ee41c90f48970fce56c782186d50a22'
POLICY_SHA='9eb54d794fd080a9adf0813c09717864d39f26fe7581fa940e3b923a50a8cb86'

@functools.lru_cache(maxsize=1)
def definitions():
 raw=DATA.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('EP pet source changed')
 source=json.loads(raw);data=client_data();pets=companion_catalog()['pet'];rows=[]
 if(source['schema']!=1 or source['client_sha256']!=CLIENT_SHA or source['catalog_sha256']!=data.manifest['catalog_sha256']or source['policy_authorization_sha256']!=POLICY_SHA):raise ValueError('EP pet source identity')
 for row in source['inventory']:
  t=row['template'];unit={723605:231,723606:232,723607:233,723608:234}.get(t);item=data.item(t)
  if(t not in(723605,723606,723607,723608)or (row['metadata'],row['group'],row['max_stack'],row['item_type'],row['flags4'],row['flags8'],row['pet_unit'],row['duration'],row['native_extra'],row['price_ep'],row['quantity'],row['limit'],row['display_category'],row['display_rank'])!=(0,4,1,12,0x401002,0x60,unit,-1,15,1000,1,None,1,t-723600)):
   raise ValueError('Unqualified EP pet contract')
  if((item['name'],item['metadata'],item['item_type'],item['flags4'],item['flags8'])!=(row['name'],0,12,0x401002,0x60)or len(item['record'])!=232 or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or struct.unpack_from('<i',item['record'],0x10)[0]!=0):raise ValueError('EP pet current item mismatch')
  if pets.get(t)!={'outcomes':[[unit,1]],'duration':-1,'native_extra':15}:raise ValueError('EP pet permanent mapping mismatch')
  with data.connect()as db:
   if db.execute('SELECT id FROM items WHERE name=?',(row['name'],)).fetchall()!=[(t,)]:raise ValueError('Ambiguous EP pet source name')
  rows.append(row)
 if [r['template']for r in rows]!=[723605,723606,723607,723608]:raise ValueError('EP pet exact scope')
 return tuple(rows)
