"""Finite registration rules and readonly account binding projection.
No DB connection, DDL, inventory-loader/writer import, producer or client effects.
"""
from pathlib import Path
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA

DATA_SHA='a14b601c32a51b2e1e86d0a19c90ba9e452d32cc79ce5139e9df53aaaddec0e9'
POLICY='cartridge-existing-singleton-register-account-v1'

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/cartridge_registration.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Cartridge registration data identity')
 p=json.loads(raw);data=client_data()
 if (p['schema_version']!=1 or p['policy_id']!=POLICY or p['official']is not False
     or p['client_sha256']!=CLIENT_SHA or p['catalog_sha256']!=data.manifest['catalog_sha256']
     or (p['initial_level'],p['initial_points'],p['duplicate_points'],p['max_points'])!=(1,0,200,50000)
     or p['overflow']!='reject_without_consume' or p['route']!='D4E_registration_only_unbound'
     or p['ownership_authorization_sha256']!='41349793189360285470fa6d0f478bcc0055a3fb9a19e9056d5d76fca220fe46'
     or p['numeric_decision_sha256']!='1e2a973535e77b370c0ff7849023c767ea20089f3a309ef6e7dfa846440f5b9f'):
  raise ValueError('Cartridge registration finite policy')
 rows=p['materials'];expected={119222+i:7+i for i in range(13)}|{119235+i:1+i for i in range(6)}
 if len(rows)!=19 or {r['template']:r['cartridge_id']for r in rows}!=expected:raise ValueError('Cartridge exact19 mapping')
 for r in rows:
  item=data.item(r['template'])
  if ((r['metadata'],r['group'],r['raw_max'],r['max_stack'])!=(0,4,0,1)
      or item['metadata']!=0 or item['item_type']!=7
      or hashlib.sha256(item['record']).hexdigest()!=r['record_sha256']):raise ValueError('Cartridge original material identity')
 return p

def materials():return tuple(dict(r)for r in catalog()['materials'])
def material(template):
 if type(template)is not int:raise ValueError('Cartridge material type')
 row=next((r for r in catalog()['materials']if r['template']==template),None)
 if row is None:raise ValueError('Unadmitted Cartridge material')
 return dict(row)

def source(item):
 row=material(item.get('template'))
 allowed={'uid','template','metadata','count','group','slot','expires_at','lock_until','sealed','seal_used'}
 if (set(item)-allowed or item.get('metadata')!=0 or item.get('count')!=1 or item.get('group')!=4
     or item.get('sealed',False)is not False or item.get('seal_used',0)!=0):raise ValueError('Cartridge singleton plain unsealed material')
 return row

def account_state(rows,points,revision):
 if type(rows)is not dict or len(rows)>19:raise ValueError('Cartridge account rows')
 if type(points)is not int or not 0<=points<=50000 or type(revision)is not int or not 0<=revision<2**63:raise ValueError('Cartridge account points/revision')
 for identity,pair in rows.items():
  if (type(identity)is not int or not 1<=identity<=19 or type(pair)not in(list,tuple)or len(pair)!=2
      or type(pair[0])is not int or not 0<=pair[0]<2**63 or type(pair[1])is not int or not 1<=pair[1]<=6):raise ValueError('Cartridge finite unbound logical state')
 positive=[pair[0]for pair in rows.values()if pair[0]]
 if len(set(positive))!=len(positive):raise ValueError('Duplicate positive Cartridge UID in current/history map')
 return dict(rows={i:(v[0],v[1])for i,v in rows.items()},points=points,revision=revision)


REGISTRATION_SCHEMAS={'account_cartridge_state': "CREATE TABLE account_cartridge_state (\n account_id INTEGER PRIMARY KEY CHECK(typeof(account_id)='integer' AND account_id>0),\n points INTEGER NOT NULL CHECK(typeof(points)='integer' AND points BETWEEN 0 AND 50000),\n revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision BETWEEN 0 AND 9223372036854775807))", 'account_cartridge_collection': "CREATE TABLE account_cartridge_collection (\n account_id INTEGER NOT NULL REFERENCES account_cartridge_state(account_id),\n cartridge_id INTEGER NOT NULL CHECK(typeof(cartridge_id)='integer' AND cartridge_id BETWEEN 1 AND 19),\n level INTEGER NOT NULL CHECK(typeof(level)='integer' AND level BETWEEN 1 AND 6),\n bound_uid INTEGER NOT NULL CHECK(typeof(bound_uid)='integer' AND bound_uid=0),\n PRIMARY KEY(account_id,cartridge_id))", 'account_cartridge_registration_receipts': "CREATE TABLE account_cartridge_registration_receipts (\n operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,\n account_id INTEGER NOT NULL REFERENCES account_cartridge_state(account_id),\n actor_uid INTEGER NOT NULL CHECK(typeof(actor_uid)='integer' AND actor_uid>=1001),\n source_uid INTEGER NOT NULL CHECK(typeof(source_uid)='integer' AND source_uid>0),\n source_template INTEGER NOT NULL, cartridge_id INTEGER NOT NULL,\n response_id INTEGER NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,\n policy_id TEXT NOT NULL)"}
# Pure readonly authority primitives. This existing rules module never imports
# inventory_state/load_items or account writer, never opens DBs, and never DDLs.
BINDING_POLICY='cartridge-finite-armor-attach-remove-zero-cost-v1'
BINDING_SCHEMAS=dict(REGISTRATION_SCHEMAS)
BINDING_SCHEMAS['account_cartridge_collection']=REGISTRATION_SCHEMAS['account_cartridge_collection'].replace('AND bound_uid=0','AND (bound_uid=0 OR bound_uid>0 AND bound_uid<9223372036854775808)')
BINDING_SCHEMAS['account_cartridge_binding_receipts']='''CREATE TABLE account_cartridge_binding_receipts (
 operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
 account_id INTEGER NOT NULL REFERENCES account_cartridge_state(account_id),
 actor_uid INTEGER NOT NULL, target_uid INTEGER NOT NULL, kind INTEGER NOT NULL CHECK(kind IN (3408,3410)),
 cartridge_id INTEGER NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
 policy_id TEXT NOT NULL)'''
LEGACY_SCHEMAS=('equipment_cartridge_states','equipment_cartridge_points')

def binding_catalog():
 b=catalog()['finite_binding']
 if (b['policy']!=BINDING_POLICY or b['numeric_decision_sha256']!='cfc158645cee3a51c0369aed82e97f45a725c7fe4fb804326c17984ccd2d95b8'
     or (b['ED'],b['materials'],b['D54'],b['replace'],b['containers'])!=(0,0,False,False,[1,9])):raise ValueError('Cartridge finite binding policy')
 targets={r['template']:r for r in b['targets']}
 if len(targets)!=60 or set(targets)!=set(range(119241,119297))|set(range(119301,119305)):raise ValueError('Cartridge finite armor targets')
 for t,r in targets.items():
  d=client_data().item(t)
  if d['metadata']!=1 or d['item_type']!=2 or d['record'][0xd5]!=r['part']or hashlib.sha256(d['record']).hexdigest()!=r['record_sha256']:raise ValueError('Cartridge target original identity')
 return targets

def scalar(value):
 if type(value)is not list or len(value)!=2 or any(type(v)is not int for v in value):raise ValueError('Cartridge pair shape')
 i,l=value
 if (i,l)!=(0,0)and not(1<=i<=19 and 1<=l<=6):raise ValueError('Cartridge scalar ID/level')
 return list(value)

def non_authority(item):
 if type(item)is not dict:raise ValueError('Non-authority Cartridge item object')
 if 'cartridge'in item and scalar(item['cartridge'])!=[0,0]:raise ValueError('Saved container scalar is not Cartridge authority')
 return item

def schema_kind(db):
 for name in LEGACY_SCHEMAS:
  if db.execute('SELECT 1 FROM sqlite_master WHERE name=? COLLATE NOCASE',(name,)).fetchone():raise ValueError('Cartridge legacy role schema HOLD')
 found={n:db.execute('SELECT type,sql FROM sqlite_master WHERE name=? COLLATE NOCASE',(n,)).fetchall()for n in GROWTH_SCHEMAS}
 if not any(found.values()):return 'absent'
 for rows in found.values():
  if rows and(len(rows)!=1 or rows[0][0]!='table'):raise ValueError('Cartridge schema object collision')
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND lower(tbl_name) IN (?,?,?,?,?) LIMIT 1",tuple(GROWTH_SCHEMAS)).fetchone():raise ValueError('Unknown Cartridge schema trigger')
 normal=lambda v:' '.join(v.split())
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND lower(tbl_name)='account_cartridge_growth_receipts' AND sql IS NOT NULL LIMIT 1").fetchone():raise ValueError('Unknown Cartridge growth receipt index')
 for name,expected in(('registration',REGISTRATION_SCHEMAS),('binding',BINDING_SCHEMAS),('binding',GROWTH_SCHEMAS)):
  if all(bool(found[k])==(k in expected)for k in GROWTH_SCHEMAS)and all(normal(found[k][0][1])==normal(sql)for k,sql in expected.items()):return name
 raise ValueError('Unknown or partial Cartridge account schema')

def _unique_json(raw):
 def pairs(rows):
  out={}
  for k,v in rows:
   if k in out:raise ValueError('Duplicate Cartridge inspection JSON')
   out[k]=v
  return out
 try:return json.loads(raw,object_pairs_hook=pairs)
 except(TypeError,json.JSONDecodeError)as exc:raise ValueError('Malformed Cartridge inspection JSON')from exc

def legacy_guard(db,account_id,kind):
 exists=lambda n:bool(db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'",(n,)).fetchone())
 def groups(g):
  if type(g)is not dict:raise ValueError('Unknown option groups')
  for k,v in g.items():
   if type(k)is not str or not k.isdecimal()or str(int(k))!=k or type(v)is not list or k=='32':raise ValueError('Unqualified option group32 or malformed groups')
 if exists('equipment_options'):
  for raw, in db.execute('SELECT e.groups_json FROM equipment_options e JOIN inventory_items i ON i.uid=e.item_uid JOIN character_owners o ON o.uid=i.owner WHERE o.account_id=?',(account_id,)):groups(_unique_json(raw))
 for table,query in(('private_bank_items','SELECT b.item_json FROM private_bank_items b JOIN character_owners o ON o.uid=b.owner WHERE o.account_id=?'),('shared_bank_items','SELECT item_json FROM shared_bank_items WHERE account_id=?')):
  if exists(table):
   for raw, in db.execute(query,(account_id,)):
    item=_unique_json(raw);non_authority(item);groups(item.get('option_groups',{}))
 growth_history_guard(db,account_id,kind)
 if exists('inventory_action_receipts'):
  for action,table in((0xd4e,'account_cartridge_registration_receipts'),(0xd50,'account_cartridge_binding_receipts'),(0xd52,'account_cartridge_binding_receipts')):
   has=kind!='absent'and(action==0xd4e or kind=='binding')
   paired='NOT EXISTS (SELECT 1 FROM '+table+' a WHERE a.operation_id=r.operation_id AND a.account_id=? AND a.actor_uid=r.owner AND a.request_hash=r.request_hash'+(' AND a.kind=r.kind'if action!=0xd4e else'')+')'if has else'1'
   args=(account_id,action,account_id)if has else(account_id,action)
   if db.execute('SELECT 1 FROM inventory_action_receipts r JOIN character_owners o ON o.uid=r.owner WHERE o.account_id=? AND r.kind=? AND '+paired+' LIMIT 1',args).fetchone():raise ValueError('Unpaired Cartridge inventory history')
 for table,action in(('account_cartridge_registration_receipts',0xd4e),('account_cartridge_binding_receipts',None)):
  if not exists(table):continue
  if not exists('inventory_action_receipts'):
   if db.execute('SELECT 1 FROM '+table+' WHERE account_id=? LIMIT 1',(account_id,)).fetchone():raise ValueError('Orphan Cartridge account history')
  else:
   condition='r.kind='+str(action)if action is not None else'r.kind=a.kind'
   if db.execute('SELECT 1 FROM '+table+' a WHERE a.account_id=? AND NOT EXISTS (SELECT 1 FROM inventory_action_receipts r WHERE r.operation_id=a.operation_id AND r.owner=a.actor_uid AND r.request_hash=a.request_hash AND '+condition+') LIMIT 1',(account_id,)).fetchone():raise ValueError('Unpaired Cartridge account history')

def _raw_target(db,uid,account_id):
 rows=db.execute('SELECT i.owner,i.template,i.metadata,i.count,i.bag_group,i.slot FROM inventory_items i JOIN character_owners o ON o.uid=i.owner WHERE i.uid=? AND o.account_id=?',(uid,account_id)).fetchall()
 if len(rows)!=1:raise ValueError('Cartridge bound UID owner/orphan')
 owner,t,meta,count,group,slot=rows[0]
 if t not in binding_catalog()or(meta,count)!=(1,1)or group not in(1,9)or type(slot)is not int or slot<0:raise ValueError('Cartridge carrier identity/container')
 from els_server.domain.bag_capacity import wire_limit
 if group==1 and slot>=wire_limit(1):raise ValueError('Cartridge carrier bag slot')
 if group==9:
  from els_server.domain.equipment_requirements import catalog as requirements
  if slot!=requirements()[1][client_data().item(t)['equip_position']]:raise ValueError('Cartridge carrier worn slot')
 for table,query in(('item_expiration','SELECT 1 FROM item_expiration WHERE item_uid=?'),('item_seals','SELECT 1 FROM item_seals WHERE item_uid=? AND sealed!=0')):
  if db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'",(table,)).fetchone()and db.execute(query,(uid,)).fetchone():raise ValueError('Inconsistent timed/sealed Cartridge binding HOLD')
 return owner,t,group,slot

def read_account(db,account_id):
 if not db.in_transaction or type(account_id)is not int or not 0<account_id<2**63:raise ValueError('Readonly Cartridge authority transaction/account')
 kind=schema_kind(db);legacy_guard(db,account_id,kind)
 if kind=='absent':return account_state({},0,0)
 row=db.execute('SELECT points,revision FROM account_cartridge_state WHERE account_id=?',(account_id,)).fetchone()
 raw=db.execute('SELECT cartridge_id,bound_uid,level FROM account_cartridge_collection WHERE account_id=? ORDER BY cartridge_id',(account_id,)).fetchall()
 if row is None:
  if raw or db.execute('SELECT 1 FROM account_cartridge_registration_receipts WHERE account_id=?',(account_id,)).fetchone():raise ValueError('Orphan Cartridge account data')
  if kind=='binding'and db.execute('SELECT 1 FROM account_cartridge_binding_receipts WHERE account_id=?',(account_id,)).fetchone():raise ValueError('Orphan Cartridge binding data')
  return account_state({},0,0)
 if not raw or row[1]<1:raise ValueError('Invalid Cartridge account state')
 out=account_state({i:(u,l)for i,u,l in raw},*row)
 if len(out['rows'])!=len(raw):raise ValueError('Duplicate Cartridge identity')
 seen=set()
 for identity,(uid,level)in out['rows'].items():
  if not uid:continue
  if kind!='binding'or uid in seen or db.execute('SELECT COUNT(*) FROM account_cartridge_collection WHERE bound_uid=?',(uid,)).fetchone()!=(1,):raise ValueError('Duplicate or unqualified Cartridge positive UID')
  seen.add(uid);_raw_target(db,uid,account_id)
 return out

def owner_account(db,owner):
 row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
 if row is None or type(row[0])is not int or row[0]<=0:raise ValueError('Cartridge inventory owner account')
 return row[0]

def project(db,items,owner):
 kind=schema_kind(db)
 # Bootstrap inventories may predate character owner schema; no state exists.
 if kind=='absent':return items
 account_id=owner_account(db,owner);current=read_account(db,account_id)
 bound={uid:[i,l]for i,(uid,l)in current['rows'].items()if uid}
 for item in items:
  if 'cartridge'in item:raise ValueError('Raw inventory scalar must not be persisted')
  if item['uid']in bound:item['cartridge']=bound[item['uid']]
 return items

def require_unbound(db,uid):
 kind=schema_kind(db)
 if kind=='binding'and db.execute('SELECT 1 FROM account_cartridge_collection WHERE bound_uid=? LIMIT 1',(uid,)).fetchone():raise ValueError('Remove Cartridge before destructive/transfer/seal action')

def require_role_unbound(db,owner,account_id):
 if schema_kind(db)=='absent':return
 current=read_account(db,account_id)
 for uid,level in current['rows'].values():
  if uid and _raw_target(db,uid,account_id)[0]==owner:raise ValueError('Remove Cartridge before character deletion')


# One-step growth is a separate policy; finite_binding.D54 remains False.
GROWTH_POLICY='cartridge-unbound-one-step-native-current-level-fees-v1'
GROWTH_RECEIPT_SQL='''CREATE TABLE account_cartridge_growth_receipts (
 operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
 account_id INTEGER NOT NULL REFERENCES account_cartridge_state(account_id),
 actor_uid INTEGER NOT NULL CHECK(typeof(actor_uid)='integer' AND actor_uid>=1001),
 cartridge_id INTEGER NOT NULL CHECK(typeof(cartridge_id)='integer' AND cartridge_id BETWEEN 1 AND 19),
 previous_level INTEGER NOT NULL CHECK(typeof(previous_level)='integer' AND previous_level BETWEEN 1 AND 5),
 before_json TEXT NOT NULL, after_json TEXT NOT NULL, policy_id TEXT NOT NULL)'''
GROWTH_SCHEMAS=dict(BINDING_SCHEMAS,account_cartridge_growth_receipts=GROWTH_RECEIPT_SQL)

def growth_catalog():
 g=catalog()['finite_growth']
 expected=dict(policy=GROWTH_POLICY,selected_unbound_only=True,minimum_current_level=1,maximum_current_level=5,maximum_level=6,
  normal_ids=list(range(7,20)),honor_ids=list(range(1,7)),
  normal_fees=[[1,100,10000000],[2,300,25000000],[3,500,65000000],[4,700,200000000],[5,1100,450000000]],
  honor_fees=[[1,200,20000000],[2,600,50000000],[3,1000,130000000],[4,1400,400000000],[5,2200,900000000]],
  current_level_source_sha256='c3612a1116dc2d959a2225bc7eeef2543c798c0c5e61d9d2aa2101e915ce4ebd',
  category_source_peer_sha256='2a5a7d93cdf081d712db22f01de1f1cd2fa46ab4db3f2975bbb2352f6c70c724',
  account_authorization_sha256='41349793189360285470fa6d0f478bcc0055a3fb9a19e9056d5d76fca220fe46')
 if g!=expected:raise ValueError('Cartridge exact original growth policy')
 return g

def growth_fee(identity,level):
 if type(identity)is not int or not 1<=identity<=19 or type(level)is not int or not 1<=level<=5:raise ValueError('Cartridge registered current growth ID/level')
 g=growth_catalog();rows=g['honor_fees']if identity in g['honor_ids']else g['normal_fees']
 key,points,ed=rows[level-1]
 if key!=level or any(type(v)is not int or v<=0 for v in(points,ed)):raise ValueError('Cartridge current level fee identity')
 return points,ed

def _growth_snapshot(raw):
 value=_unique_json(raw)
 if type(value)is not dict or set(value)!={'account','wallet'}:raise ValueError('Cartridge growth snapshot shape')
 a=value['account'];wallet=value['wallet']
 if type(a)is not dict or set(a)!={'rows','points','revision'}or type(a['rows'])is not list:raise ValueError('Cartridge growth account shape')
 rows={}
 for r in a['rows']:
  if type(r)is not list or len(r)!=3 or type(r[0])is not int or r[0]in rows:raise ValueError('Cartridge growth historical collection')
  rows[r[0]]=(r[1],r[2])
 account=account_state(rows,a['points'],a['revision'])
 if not rows or account['revision']<1:raise ValueError('Cartridge growth historical account empty')
 if type(wallet)is not dict or set(wallet)!={'ed','experience','revision'}or any(type(v)is not int or not 0<=v<2**63 for v in wallet.values()):raise ValueError('Cartridge growth historical wallet')
 return dict(account=account,wallet=wallet)

def growth_history_pair(row,generic):
 # Pure receipt proof, used by readers and retries; no current actor clock/class
 # reinterpretation, storage/writer import, new source or current-state writes.
 import struct
 if row is None or generic is None or len(row)!=9 or len(generic)!=7:raise ValueError('Cartridge growth missing paired history')
 op,digest,account,actor,identity,level,before_raw,after_raw,policy=row
 if(type(op)is not str or not 1<=len(op)<=160 or type(digest)is not str
    or type(account)is not int or not 0<account<2**63 or type(actor)is not int or not 1001<=actor<2**63
    or type(identity)is not int or not 1<=identity<=19 or type(level)is not int or not 1<=level<=5 or policy!=GROWTH_POLICY):raise ValueError('Cartridge growth receipt identity types')
 expected_hash=hashlib.sha256(str(actor).encode()+b':'+str(0xd54).encode()+b':'+struct.pack('>i',identity)).hexdigest()
 if digest!=expected_hash or generic[:4]!=(op,digest,actor,0xd54):raise ValueError('Cartridge growth paired request/owner/kind')
 if any(_unique_json(raw)!=[]for raw in generic[4:]):raise ValueError('Cartridge unbound growth must not change item positions')
 before,after=_growth_snapshot(before_raw),_growth_snapshot(after_raw)
 a,b=before['account'],after['account'];w,z=before['wallet'],after['wallet']
 points,ed=growth_fee(identity,level)
 if a['rows'].get(identity)!=(0,level):raise ValueError('Cartridge growth original ID was not unbound/current')
 rows=dict(a['rows']);rows[identity]=(0,level+1)
 if(b['rows']!=rows or b['points']!=a['points']-points or b['revision']!=a['revision']+1
    or z!=dict(w,ed=w['ed']-ed,revision=w['revision']+1)):raise ValueError('Cartridge growth original exact fee/level/revision transition')
 return before,after

def growth_history_guard(db,account_id,kind):
 exists=lambda n:bool(db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'",(n,)).fetchone())
 growth=exists('account_cartridge_growth_receipts');inventory=exists('inventory_action_receipts')
 generic=[]
 if inventory:
  generic=db.execute('SELECT r.operation_id,r.request_hash,r.owner,r.kind,r.positions_json,r.before_json,r.after_json FROM inventory_action_receipts r JOIN character_owners o ON o.uid=r.owner WHERE o.account_id=? AND r.kind=?',(account_id,0xd54)).fetchall()
 if generic and(not growth or kind!='binding'):raise ValueError('Unknown/unpaired Cartridge growth history HOLD')
 dedicated=db.execute('SELECT * FROM account_cartridge_growth_receipts WHERE account_id=?',(account_id,)).fetchall()if growth else[]
 by_op={r[0]:r for r in dedicated};by_generic={r[0]:r for r in generic}
 if len(by_op)!=len(dedicated)or len(by_generic)!=len(generic)or set(by_op)!=set(by_generic):raise ValueError('Unpaired Cartridge growth account/actor history')
 for op,row in by_op.items():
  if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(row[3],)).fetchone()!=(account_id,):raise ValueError('Cartridge growth historical actor account')
  before,after=growth_history_pair(row,by_generic[op])
  current=db.execute('SELECT level FROM account_cartridge_collection WHERE account_id=? AND cartridge_id=?',(account_id,row[4])).fetchone()
  revision=db.execute('SELECT revision FROM account_cartridge_state WHERE account_id=?',(account_id,)).fetchone()
  wallet=db.execute('SELECT revision FROM reward_balances WHERE uid=?',(row[3],)).fetchone()
  if(current is None or current[0]<after['account']['rows'][row[4]][1]or revision is None or revision[0]<after['account']['revision']
     or wallet is None or type(wallet[0])is not int or wallet[0]<after['wallet']['revision']):raise ValueError('Cartridge growth current state regressed or orphaned')
