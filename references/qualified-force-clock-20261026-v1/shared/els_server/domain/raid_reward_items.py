"""Finite native raid item readers and transaction-bound acquisition sources."""
import functools,hashlib,json,sqlite3
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA

@functools.lru_cache(maxsize=1)
def catalog():
 p=Path(__file__).resolve().parents[1]/'data/raid_reward_items.json';raw=p.read_bytes()
 m=json.loads(p.with_suffix('.manifest.json').read_bytes());d=json.loads(raw);c=client_data()
 if (hashlib.sha256(raw).hexdigest()!=m['payload_sha256'] or m['client_sha256']!=CLIENT_SHA
     or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']
     or d['policy']!='formal-raid-reward-items-20261025-v1' or d['schema_version']!=1):raise ValueError('Raid reward item catalog identity')
 for r in d['items']:
  item=c.item(r['template'])
  if (hashlib.sha256(item['record']).hexdigest()!=r['record_sha256']or item['metadata']!=r['metadata']
      or item['item_type']!=r['item_type']or item['name']!=r['name']):raise ValueError('Raid exact native item identity')
  if not r['already_registered'] and (r['item_type']not in(6,7)or r['group']!=(3 if r['item_type']==6 else 4)
      or r['max_stack']!=max(1,r['raw_max_stack'])):raise ValueError('Raid finite new reader classification')
 return d

def definitions():return tuple(catalog()['items'])
def boxes():
 from els_server.domain.formal_pve_economy import policy as ordinary_policy
 result=dict(catalog()['boxes']);extra=ordinary_policy()['native_bundle_boxes']
 if set(result)&set(extra):raise ValueError('Conflicting exact native bundle identity')
 return {**result,**extra}
def source_only_templates():
 # Existing generic grants remain closed for new readers, Cartridge materials,
 # black fragments and original owned-only accessory readers. Other already
 # supported ordinary materials/weapons keep their previous acquisition rules.
 from els_server.domain.equipment_circuit_rules import catalog as circuit_catalog
 from els_server.game_data import client_data
 c=client_data()
 from els_server.domain.formal_pve_economy import policy as ordinary_policy
 return frozenset(catalog()['new_material_readers'])|frozenset(ordinary_policy()['new_reader_ids'])|frozenset(int(t)for t in circuit_catalog()['materials']if c.item(int(t))['name'].startswith('T-'))

def plain_plan(plan):return json.dumps(plan,sort_keys=True,separators=(',',':'))
def ensure_sources(db):
 if not db.in_transaction:raise ValueError('Raid source schema requires original writer')
 db.execute('''CREATE TABLE IF NOT EXISTS raid_reward_sources (
 operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL,kind TEXT NOT NULL,
 source_json TEXT NOT NULL,plan_json TEXT NOT NULL)''')

_SEAL=object()
class _RaidSource:
 __slots__=('_seal','_db','owner','operation','kind','_source','_plan','_guard','_path')
 def __init__(self,seal,db,owner,operation,kind,source,plan,guard):
  if seal is not _SEAL:raise ValueError('Raid source constructor is private')
  self._seal=seal;self._db=db;self.owner=owner;self.operation=operation;self.kind=kind
  self._source=plain_plan(source);self._plan=plain_plan(plan);self._guard=guard
  self._path=Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()
 def _validate(self):
  if self._seal is not _SEAL or type(self._db)is not sqlite3.Connection or not self._db.in_transaction:
   raise ValueError('Raid acquisition source outside original writer')
  if self._guard(self._db) is not True:raise ValueError('Raid acquisition authority expired')
  row=self._db.execute('SELECT owner,kind,source_json,plan_json FROM raid_reward_sources WHERE operation_id=?',(self.operation,)).fetchone()
  if row!=(self.owner,self.kind,self._source,self._plan):raise ValueError('Raid acquisition source ledger changed')
  return self
 def validate_plan(self,plan):
  self._validate()
  if plain_plan(plan)!=self._plan:raise ValueError('Raid acquisition plan changed')
  return self
 def validate_template(self,template):
  self._validate()
  if type(template)is not int or template not in {r['template']for r in json.loads(self._plan)}:raise ValueError('Raid acquisition template outside exact plan')
  return self
 def validate_qualified_force_book(self,template,*,replay_only=False):
  self.validate_template(template)
  if type(replay_only)is not bool:raise ValueError('Master active Force receipt scope')
  maps={311066:(34380,),311515:(34420,),311521:(34460,),311512:(34400,),311518:(34440,),311524:(34480,),311527:(34500,34700)}
  source=json.loads(self._source);mid=source.get('dungeon')
  from els_server.domain.formal_pve_economy import policy,definition
  if(template not in maps or mid not in maps[template] or self.kind!='ordinary' or source.get('reward_source')!='local-full-native-clear-current-display-pool' or source.get('owner')!=self.owner or source.get('run')!=self.operation or source.get('graph_sha256')!=definition(mid)['graph_sha256']):raise ValueError('Exact Master active Force original full-clear source required')
  old=self._db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(self.operation,)).fetchone()
  if old is not None:
   saved=json.loads(old[0])
   if saved.get('raid_reward_source')!=self.receipt_identity() or saved.get('items')!=json.loads(self._plan):raise ValueError('Master active Force committed source changed')
   return self
  if replay_only or source.get('policy_sha256')!=policy()['_sha256']:raise ValueError('New Master active Force source closed or policy changed')
  return self
 def validate_clock_force_book(self,template,*,replay_only=False):
  self.validate_template(template)
  if type(replay_only)is not bool:raise ValueError('Clock Force receipt scope')
  source=json.loads(self._source);mid=source.get('dungeon')
  from els_server.domain.formal_pve_economy import policy,definition
  if(template!=295750 or mid!=34060 or self.kind!='ordinary' or source.get('reward_source')!='local-full-native-clear-current-display-pool' or source.get('owner')!=self.owner or source.get('run')!=self.operation or source.get('graph_sha256')!=definition(mid)['graph_sha256']):raise ValueError('Exact Clock Force original full-clear source required')
  old=self._db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(self.operation,)).fetchone()
  if old is not None:
   saved=json.loads(old[0])
   if saved.get('raid_reward_source')!=self.receipt_identity() or saved.get('items')!=json.loads(self._plan):raise ValueError('Clock Force committed source changed')
   return self
  if replay_only or source.get('policy_sha256')!=policy()['_sha256'] or template not in {t for pool in definition(mid)['current_display_pool'].values()for t in pool}:raise ValueError('New Clock Force source closed or policy changed')
  return self
 def bind_factory(self,db,owner,plan):
  if db is not self._db or owner!=self.owner or Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()!=self._path:
   raise ValueError('Raid acquisition foreign factory writer/owner')
  self.validate_plan(plan)
  if any(r['template']in(311066,311515,311521,311512,311518,311524,311527)for r in plan)and self._db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(self.operation,)).fetchone():raise ValueError('Committed Master active Force source is receipt-only')
  if any(r['template']==295750 for r in plan)and self._db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(self.operation,)).fetchone():raise ValueError('Committed Clock Force source is receipt-only')
  return self
 def receipt_identity(self):
  self._validate();return dict(owner=self.owner,operation=self.operation,kind=self.kind,source_sha256=hashlib.sha256(self._source.encode()).hexdigest(),plan_sha256=hashlib.sha256(self._plan.encode()).hexdigest())

def validate_source(source):
 if type(source)is not _RaidSource:raise ValueError('Typed original raid source required')
 return source._validate()

def _issue_source(db,owner,operation,kind,source,plan,guard):
 """Only called after a phase or owned-box writer has validated its authority."""
 if kind not in('phase','box','pity','ordinary')or not callable(guard)or guard(db)is not True:raise ValueError('Raid writer source authority')
 if type(owner)is not int or owner<1001 or not isinstance(plan,list)or not 1<=len(plan)<=36:raise ValueError('Raid source owner/plan')
 from els_server.storage.item_actor import require_active_character
 require_active_character(db,owner);ensure_sources(db)
 row=(owner,kind,plain_plan(source),plain_plan(plan))
 previous=db.execute('SELECT owner,kind,source_json,plan_json FROM raid_reward_sources WHERE operation_id=?',(operation,)).fetchone()
 if previous is None:db.execute('INSERT INTO raid_reward_sources VALUES (?,?,?,?,?)',(operation,*row))
 elif previous!=row:raise ValueError('Conflicting raid reward source')
 return _RaidSource(_SEAL,db,owner,operation,kind,source,plan,guard)

def entry_outputs(template,character):
 row=boxes().get(str(template))
 if row is None:raise ValueError('Unknown raid reward box')
 if row['mode']in('class_weapon','class_select'):
  family=str(client_data().unit(character['unit_class'])['unitType']);outputs=row['outputs_by_family'].get(family)
  if outputs is None:raise ValueError('Raid weapon box exact current class')
  preview=[dict(outputs[0])]
  if row['mode']=='class_select':preview.append(dict(template=row['alternative'],quantity=1))
  return dict(row,entries=preview),[dict(r)for r in outputs]
 return row,[dict(r)for r in row['entries']]
