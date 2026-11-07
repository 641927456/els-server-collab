"""Current Elysion trees: native pool and explicitly approved virtual ED values."""
import collections,functools,hashlib,json,secrets,struct
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data
from els_server.protocol.purifier_exchange_messages import ExchangeRequest

@functools.lru_cache(maxsize=1)
def catalog():
 p=Path(__file__).resolve().parents[1]/'data/secret_fragment_exchange.json';raw=p.read_bytes();d=json.loads(raw);c=client_data()
 if(hashlib.sha256(raw).hexdigest()!='d6990601d21596437186c571fd8d0eabb2976373edf20e56f584da767ac851ad'
    or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']):raise ValueError('Native tree source identity')
 enum=c.resource('Enum.lua')
 if(d['town']!=enum['VILLAGE_MAP_ID']['VMI_ELYSION']or set(d['houses'])!={enum['HOUSE_ID']['HI_ELYSION_RED_TREE'],enum['HOUSE_ID']['HI_ELYSION_BLUE_TREE']}
    or d['exchange_type']!=enum['ITEM_EXCHANGE_TYPE']['IET_DIRECT_RANDOM']or sum(r['weight']for r in d['pool'])!=10000):raise ValueError('Native tree selection/pool')
 for row in d['definitions']:
  item=c.item(row['template'])
  if(item['name']!=row['name']or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):raise ValueError('Native tree item identity')
 return d

def request(payload,town):
 if type(payload)is not bytes or len(payload)!=37:raise ValueError('Native tree request width')
 r=ExchangeRequest(*struct.unpack('>iQiiiiiBi',payload));d=catalog()
 if(town!=d['town']or r.house not in d['houses']or r.source_uid!=0 or r.source!=d['source']or r.source_quantity!=d['source_quantity']
    or r.destination!=0 or r.exchange_type!=d['exchange_type']or r.quantity<1 or r.native_flag!=1 or r.native_index!=0):raise ValueError('Native tree exact selection')
 return r

def draw(quantity,randbelow=None):
 randbelow=secrets.randbelow if randbelow is None else randbelow
 items=collections.Counter();ed=0
 for _ in range(quantity):
  ticket=randbelow(10000)
  if type(ticket)is not int or not 0<=ticket<10000:raise ValueError('Native tree RNG range')
  for row in catalog()['pool']:
   if ticket<row['weight']:
    if row['ED']:ed+=row['ED']*row['quantity']
    else:items[row['template']]+=row['quantity']
    break
   ticket-=row['weight']
 return items,ed
