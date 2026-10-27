"""Exact owned30880 consumer; the approved numeric increment is a local rule."""
from pathlib import Path
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='1a835a787da47d5aaf39bf8a404df322ba44069b1681a1305c0494f1e38ca473'
POLICY='feta-owned-marcus-gauge-20261026-v1'
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/feta_gauge.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Gauge exact approved bytes')
 p=json.loads(raw);d=client_data();item=d.item(30880)
 if(p['schema']!=1 or p['policy']!=POLICY or p['client_sha256']!=CLIENT_SHA
 or p['catalog_sha256']!=d.manifest['catalog_sha256']
 or p['authorization_sha256']!='8cc392303ec27607460e9619caaa56863579af69d4ea8371a53eee50c220e253'
 or(p['template'],p['metadata'],p['group'],p['max_stack'],p['count'],p['ED'],p['progress'],p['gain'],p['maximum'])!=(30880,2,4,500,1,0,'accessory:3',2,100)
 or p['local_rule']is not True or p['full']!='refuse_without_consumption'
 or p['direct_box_grant']is not False or p['weekly_count_changed']is not False
 or item['metadata']!=2 or hashlib.sha256(item['record']).hexdigest()!=p['record_sha256']):raise ValueError('Gauge current raw item and approved policy')
 return p

def definition():
 p=catalog();return p['metadata'],p['group'],p['max_stack']

def require_production():
 from els_server.storage.feta_gauge import WRITER_ENABLED
 from els_server.domain.feta_gauge_flow import WRITER_ENABLED as FLOW_ENABLED
 if not WRITER_ENABLED or not FLOW_ENABLED:raise ValueError('Gauge consumer closed; source closed')
 catalog()

def plain(item):
 base={'uid','template','metadata','count','group','slot'}
 return (item.get('template')==30880 and item.get('metadata')==2 and item.get('group')==4
 and type(item.get('count'))is int and 1<=item['count']<=500 and base<=item.keys()
 and item.keys()<=base|{'expires_at','lock_until','sealed','seal_used'}
 and item.get('sealed',False)is False and item.get('seal_used',0)==0)

class _GaugeAuthority:
 def __init__(self,s,e,sequence,operation):
  self.s=s;self.e=e;self.sequence=sequence;self.operation=operation;self.payload=e.payload
  self.account=s.account;self.store=self.account.store;self.root=self.account.root
  self.app=getattr(s,'application',None);self.identity=getattr(s,'identity',None)
  self.registry=getattr(self.app,'registry',None);self.local_app=getattr(s,'_chip_reset_local_application',None)
  self.owner=self.account.uid;self.account_id=self.account.account_id;self.shop=s.shop_session_id
  self.path=Path(self.store.path).resolve()
  if not self():raise ValueError('Gauge captured current actor')
 def __call__(self):
  from els_server.domain.equipment_chip_flow import reset_context
  from els_server.storage.feta_gauge import WRITER_ENABLED
  from els_server.domain.feta_gauge_flow import WRITER_ENABLED as FLOW_ENABLED
  s,a,e=self.s,self.account,self.e
  try:reset_context(s,e,self.sequence)
  except(ValueError,AttributeError):return False
  return bool(WRITER_ENABLED and FLOW_ENABLED and s.client_build=='dx11_260923'
   and e.event_id==0x202 and e.kind==0x219 and type(e.payload)is bytes and e.payload==self.payload
   and s.account is a and a.store is self.store and a.root is self.root
   and getattr(s,'application',None)is self.app and getattr(s,'identity',None)is self.identity
   and getattr(self.app,'registry',None)is self.registry and getattr(s,'_chip_reset_local_application',None)is self.local_app
   and(a.uid,a.account_id,s.shop_session_id,self.store.uid)==(self.owner,self.account_id,self.shop,self.owner)
   and Path(self.store.path).resolve()==self.path
   and self.operation==self.shop+':feta-gauge-v1:'+str(self.owner)+':'+str(self.sequence))
