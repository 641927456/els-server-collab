"""Finite current BlackMarketData plus separately labelled server choices."""
from pathlib import Path
import datetime,functools,hashlib,json,secrets
from els_server.game_data import CLIENT_SHA,client_data
POLICY='black-market-native-20261026-v1'
DATA_SHA='177ef8189e21aa15afdc64591c7df2aa5c6fe838ed16117249b1f8d270992135'
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/black_market.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Market reviewed policy identity')
 c=json.loads(raw);client=client_data()
 if(c['schema']!=1 or c['policy']!=POLICY or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client.manifest['catalog_sha256']
    or [len(c['tiers'][str(n)]['entries'])for n in range(1,6)]!=[6,7,7,8,6]or len(c['items'])!=20):raise ValueError('Market finite native source')
 if tuple(c['native'][k]for k in('town','scene','house','npc','button','weekly_source','ticket_cap','bid_seconds','min_online','max_online','large_from'))!=(1012,1214,40326,10500,65,35940,2,10,6,11,9):raise ValueError('Market original constants')
 for row in c['items']:
  d=client.item(row['template'])
  if(hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']or d['item_type']not in(6,7)or d['metadata']!=row['metadata']
     or row['group']!=(3 if d['item_type']==6 else 4)or row['max_stack']<1):raise ValueError('Market exact native reader')
 return c
def definitions():return tuple(catalog()['items'])
def window(now):
 if type(now)is not int or not 1<=now<2**31:raise ValueError('Market authoritative clock')
 utc8=datetime.timezone(datetime.timedelta(hours=8));d=datetime.datetime.fromtimestamp(now,utc8)
 for day in range(8):
  v=(d+datetime.timedelta(days=day)).replace(hour=20,minute=0,second=0,microsecond=0)
  start=int(v.timestamp());end=start+360
  if v.weekday()in(1,5)and end>now:return start,end
 raise ValueError('Market schedule projection')
def partition(n,local=False):
 if type(n)is not int or not 0<=n<=4096:raise ValueError('Market real queue bound')
 if local:return [1]*n
 if n<6:return []
 groups=(n+10)//11;q,r=divmod(n,groups);sizes=[q+1]*r+[q]*(groups-r)
 if sum(sizes)!=n or not all(6<=v<=11 for v in sizes):raise ValueError('Market balanced real rooms')
 return sizes
def draw(total,randbelow=secrets.randbelow):
 if total not in(3,4):raise ValueError('Market lot count')
 c=catalog();weights=c['local']['tier_weights'];out=[]
 def choose(n):
  x=randbelow(n)
  if type(x)is not int or not 0<=x<n:raise ValueError('Market random range')
  return x
 for index in range(1,total+1):
  x=choose(sum(weights));tier=0
  for tier,w in enumerate(weights,1):
   if x<w:break
   x-=w
  d=c['tiers'][str(tier)];row=d['entries'][choose(len(d['entries']))]
  out.append(dict(index=index,tier=tier,**row,opening=d['min_ed'],price=0,winner=0,settled=False))
 return out
def minimum(lot):return lot['opening']if not lot['price']else lot['price']*105//100
