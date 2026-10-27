"""Five exact original Feta fragment recipes; no random draw or extra sources."""
from pathlib import Path
from uuid import UUID
import functools,hashlib,json,struct
from els_server.game_data import client_data,CLIENT_SHA

DATA_SHA='dfd2f67d99b5a475d155c6e99f765499879188b914f17cab88eef9a051dba361'
POLICY='feta-nine-original-exchanges-20261026-v2'
SOURCE=119216

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/feta_exchange.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Feta exact policy bytes')
 p=json.loads(raw);data=client_data()
 if(p['schema']!=1 or p['policy']!=POLICY or p['client_sha256']!=CLIENT_SHA
    or p['catalog_sha256']!=data.manifest['catalog_sha256']or p['house']!=40326
    or p['town']!=1012 or p['scene']!=1214 or p['ED']!=0
    or p['local_rule']is not True or p['authorization_sha256']!='c9836d31bc1f892d51e60c5f5c7d3612d4dd1798b608aa60d4e8306663ee4585'
    or {r['index']for r in p['recipes']}!=(set(range(674,679))|{686,687,689,690})):raise ValueError('Feta finite policy')
 expected=[(674+n,3,119216,80,119217+n,1,25)for n in range(4)]+[(678,1,119216,60,119323,1,100),(686,3,119317,20,710313,20,50),(687,3,119317,20,710193,20,50),(689,3,119317,120,119328,1,50),(690,1,119317,300,119216,4,100)]
 if[(r['index'],r['type'],r['source'],r['source_quantity'],r['destination'],r['destination_quantity'],r['raw_rate'])for r in p['recipes']]!=expected:raise ValueError('Feta current original five rows')
 for row in p['items']:
  d=data.item(row['template'])
  if d['metadata']!=row['metadata']or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256']:raise ValueError('Feta current item record')
 return p

def request(payload):
 if type(payload)is not bytes or len(payload)!=37:raise ValueError('Feta original223 request length')
 house,uid,source,source_quantity,destination,kind,quantity,flag,index=struct.unpack('>iQiiiiiBi',payload)
 if(house!=40326 or uid!=0 or source not in(119216,119317) or quantity!=1 or flag!=1 or index!=0):raise ValueError('Feta exact native envelope')
 row=next((r for r in catalog()['recipes']if r['type']==kind and r['source']==source and r['source_quantity']==source_quantity and (destination==r['destination']if kind==3 else destination==0)),None)
 if row is None:raise ValueError('Feta unadmitted recipe')
 return row

def plain_source(item,source=SOURCE):
 from els_server.domain.cartridge_exchange_rules import plain_source as original
 return source in(119216,119317)and item.get('template')==source and original({**item,'template':SOURCE})

class _FetaAuthority:
 def __init__(self,session,event,sequence,operation):
  self.session=session;self.account=session.account;self.store=self.account.store
  self.root=getattr(self.account,'root',None);self.app=getattr(session,'application',None)
  self.local_app=getattr(session,'_cartridge40326_local_application',None);self.identity=getattr(session,'identity',None)
  self.owner=self.account.uid;self.account_id=self.account.account_id;self.path=Path(self.store.path).resolve()
  self.shop=session.shop_session_id;self.payload=event.payload;self.event=event;self.sequence=sequence;self.operation=operation
  if not self():raise ValueError('Feta captured current actor')
 def __call__(self):
  from els_server.domain.feta_exchange_flow import WRITER_ENABLED as FLOW_ENABLED
  from els_server.storage.feta_exchange import WRITER_ENABLED
  from els_server.domain.cartridge_exchange_flow import _context
  s,a,e=self.session,self.account,self.event
  try:valid_nonce=type(self.shop)is str and str(UUID(self.shop))==self.shop and UUID(self.shop).version==4
  except ValueError:return False
  return bool(WRITER_ENABLED and FLOW_ENABLED and valid_nonce and s.account is a and a.store is self.store
   and getattr(a,'root',None)is self.root and getattr(s,'application',None)is self.app
   and getattr(s,'_cartridge40326_local_application',None)is self.local_app and getattr(s,'identity',None)is self.identity
   and(a.uid,a.account_id,self.store.uid)==(self.owner,self.account_id,self.owner)
   and Path(self.store.path).resolve()==self.path and s.shop_session_id==self.shop
   and type(self.sequence)is int and 1<=self.sequence<2**32
   and self.operation==self.shop+':feta-exchange-v1:'+str(self.owner)+':'+str(self.sequence)
   and e.event_id==0x202 and e.kind==0x223 and e.performers==(0,)
   and e.uid==e.target_uid==2**64-1 and e.payload_mode==0 and e.payload==self.payload
   and _context(s)is True)
