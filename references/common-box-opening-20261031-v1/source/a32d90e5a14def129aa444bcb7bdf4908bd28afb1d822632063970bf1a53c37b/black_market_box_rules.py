"""Exact owned black-market boxes, independent of raid/recipe grant authority."""
from pathlib import Path
import functools,hashlib,json,sqlite3
from els_server.game_data import CLIENT_SHA,client_data
DATA_SHA='9c3ab930bcfd99f4379274fd8dd8f9d4222b99cbaf643a491bfd4492e2fe0d80'
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/black_market_boxes.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Market box policy identity')
 c=json.loads(raw);native=client_data()
 if c['schema']!=1 or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=native.manifest['catalog_sha256']:raise ValueError('Market box current build')
 from els_server.domain import equipment_circuit_rules as circuits
 if hashlib.sha256((Path(circuits.__file__).resolve().parents[1]/'data/equipment_circuits.json').read_bytes()).hexdigest()!=c['circuit_policy_sha256']:raise ValueError('Market box original circuit policy changed')
 for key,row in c['boxes'].items():
  if str(row['template'])!=key or hashlib.sha256(native.item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Market box native identity')
  for r in row['entries']:
   if hashlib.sha256(native.item(r['template'])['record']).hexdigest()!=r['record_sha256']or r['quantity']!=1:raise ValueError('Market box native output')
 return c
def boxes():return catalog()['boxes']
def row(template):return boxes().get(str(template))
def entry(template):
 r=row(template)
 if r is None:raise ValueError('Unknown finite market box')
 return dict(r,selection_count=int(r['mode']=='select'))
def plan(template,choices,option,randbelow):
 r=entry(template)
 if option not in (0,1):raise ValueError('This finite native box has no option request')
 if r['mode']=='select':
  if len(choices)!=1:raise ValueError('Select exactly one native box output')
  selected=next((v for v in r['entries']if v['template']==choices[0]),None)
  if selected is None:raise ValueError('Box choice outside current finite pool')
 else:
  if choices:raise ValueError('Random/fixed box cannot accept a choice')
  n=randbelow(len(r['entries']))if r['mode']=='random'else 0
  if type(n)is not int or not 0<=n<len(r['entries']):raise ValueError('Market box random range')
  selected=r['entries'][n]
 options=r.get('options_by_template',{}).get(str(selected['template']))
 if options is not None:
  from els_server.domain.equipment_circuit_rules import validate_material
  options={'1':validate_material(selected['template'],options['1'])}
 return [dict(template=selected['template'],quantity=1,metadata=selected['metadata'],group=selected['group'])],options

_SEAL=object()
class _Source:
 __slots__=('seal','db','owner','account_id','before','plan','options','authorize')
 def __init__(self,seal,db,owner,account_id,before,plan,options,authorize):
  if seal is not _SEAL:raise ValueError('Private original market box source')
  self.seal=seal;self.db=db;self.owner=owner;self.account_id=account_id;self.before=dict(before);self.plan=[dict(r)for r in plan];self.options=options;self.authorize=authorize
 def validate(self):
  if self.seal is not _SEAL or type(self.db)is not sqlite3.Connection or not self.db.in_transaction or self.authorize()is not True:raise ValueError('Market box obsolete original transaction')
  if self.db.execute('SELECT account_id FROM character_owners WHERE uid=?',(self.owner,)).fetchone()!=(self.account_id,):raise ValueError('Market box owner changed')
  r=self.db.execute('SELECT template,count,owner FROM inventory_items WHERE uid=?',(self.before['uid'],)).fetchone()
  expected=None if self.before['count']==1 else(self.before['template'],self.before['count']-1,self.owner)
  if r!=expected:raise ValueError('Market box original debit is not present')
  return self
 def validate_plan(self,plan):
  self.validate()
  if plan!=self.plan:raise ValueError('Market box exact selected plan changed')
  return self
 def bind_factory(self,db,owner,plan):
  if db is not self.db or owner!=self.owner:raise ValueError('Market box foreign factory')
  return self.validate_plan(plan)
 def admit_template(self,template):
  self.validate()
  return template in {r['template']for r in self.plan}
def validate_source(source):
 if type(source)is not _Source:raise ValueError('Typed original market box source required')
 return source.validate()
def issue_source(db,owner,account_id,before,plan,options,authorize):
 r=entry(before['template']);allowed={v['template']for v in r['entries']}
 if len(plan)!=1 or plan[0]['template']not in allowed or plan[0]['quantity']!=1:raise ValueError('Market box limited native output plan')
 if options!=r.get('options_by_template',{}).get(str(plan[0]['template'])):raise ValueError('Market box exact native option source')
 return _Source(_SEAL,db,owner,account_id,before,plan,options,authorize).validate()
