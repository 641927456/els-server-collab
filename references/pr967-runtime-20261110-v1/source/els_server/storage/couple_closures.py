"""Exact lazy closure ledger for human-approved free couple1 farewell.
Old pair/acceptance/proposal/debit facts remain immutable; only active memberships
are removed. No ED/inventory/refund writer and no guessed marriage policy.
"""
import json
from els_server.storage import relationships as rel
from els_server.protocol.relationship_messages import farewell_request
from els_server.protocol.protocol_codec import encode_event
TABLE='native_couple_closures_v1'
POLICY='human-free-couple1-no-ring-refund-20261029-v1'
SCHEMA="CREATE TABLE native_couple_closures_v1(pair_id TEXT PRIMARY KEY REFERENCES native_couple_pairs_v1(id),operation TEXT NOT NULL UNIQUE,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,account_id INTEGER NOT NULL,peer INTEGER NOT NULL,peer_account INTEGER NOT NULL,created_at INTEGER NOT NULL,fee INTEGER NOT NULL CHECK(fee=0),refund INTEGER NOT NULL CHECK(refund=0),before_json TEXT NOT NULL,after_json TEXT NOT NULL,payload BLOB NOT NULL,policy TEXT NOT NULL,version INTEGER NOT NULL CHECK(version=1))"

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))

def present(db,*,base=True):
 found=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE lower(name)=?",(TABLE,)))
 if found and(found!={TABLE:SCHEMA}or not base):raise ValueError('Unknown or orphan couple closure schema')
 if db.execute("SELECT 1 FROM sqlite_master WHERE lower(tbl_name)=?AND(type='trigger'OR(type='index'AND sql IS NOT NULL)) LIMIT 1",(TABLE,)).fetchone():raise ValueError('Unreviewed couple closure schema extension')
 return bool(found)

def initialize(db):
 if not db.in_transaction:raise ValueError('Couple closure outside writer transaction')
 if not rel._present(db):raise ValueError('Couple closure requires original accepted schema')
 if not present(db):db.execute(SCHEMA)
 present(db)

def pair_row(db,pair_id):
 row=db.execute('SELECT *FROM native_couple_pairs_v1 WHERE id=?',(pair_id,)).fetchone()
 if row is None:raise ValueError('Missing original couple pair')
 return row

def receipt_before(pair,owner,account):
 return canonical(dict(pair=list(pair),members=sorted([[pair[1],pair[3],pair[0]],[pair[2],pair[4],pair[0]]]),actor=[owner,account]))

def receipt_after(pair_id):return canonical(dict(pair_id=pair_id,members=[],fee_ED=0,ring_refund=False))

def checked(db,row):
 pair_id,operation,digest,owner,account,peer,peer_account,stamp,fee,refund,before,after,payload,policy,version=row
 pair=pair_row(db,pair_id)
 if(type(operation)is not str or not 1<=len(operation)<=160 or payload!=b''or digest!=rel._digest(owner,0x41c,payload)
  or(owner,account,peer,peer_account)not in((pair[1],pair[3],pair[2],pair[4]),(pair[2],pair[4],pair[1],pair[3]))
  or type(stamp)is not int or not pair[5]<=stamp<2**63 or fee!=0 or refund!=0 or policy!=POLICY or version!=1
  or before!=receipt_before(pair,owner,account)or after!=receipt_after(pair_id)):raise ValueError('Couple closure immutable source receipt changed')
 rel._pair_snapshot(db,pair_id,owner,account,closed=True)
 return pair_id

def closed_pairs(db,owner,account):
 if not present(db):return set()
 rows=db.execute('SELECT c.*FROM native_couple_closures_v1 c LEFT JOIN native_couple_pairs_v1 p ON p.id=c.pair_id WHERE c.owner=?OR c.peer=?OR p.a=?OR p.b=?',(owner,owner,owner,owner)).fetchall()
 result=set()
 for row in rows:
  ident=checked(db,row);pair=pair_row(db,ident)
  if(owner,account)not in((pair[1],pair[3]),(pair[2],pair[4])):raise ValueError('Couple closed history owner changed')
  result.add(ident)
 return result

def quote(db,owner,account):
 saved=rel.snapshot(db,owner,account)
 if saved is None or saved['kind']!=1:raise ValueError('Farewell requires current couple1')
 pair=pair_row(db,saved['pair_id']);peer=saved['peer_uid'];peer_account=pair[4]if owner==pair[1]else pair[3]
 other=rel.snapshot(db,peer,peer_account)
 if other is None or(other['pair_id'],other['peer_uid'])!=(saved['pair_id'],owner):raise ValueError('Farewell reciprocal pair changed')
 return dict(saved,owner=owner,account_id=account,peer_account=peer_account)

def perform(db,owner,account,payload,operation,expected,*,guard,encode,now=None):
 farewell_request(payload)
 if type(operation)is not str or not 1<=len(operation)<=160:raise ValueError('Couple closure operation')
 if not db.in_transaction:raise ValueError('Farewell requires caller writer')
 guard(db);rel._write_guard(db);rel._actor(db,owner,account)
 if present(db):
  previous=db.execute('SELECT *FROM native_couple_closures_v1 WHERE operation=?',(operation,)).fetchone()
  if previous is not None:
   checked(db,previous)
   if previous[3:5]!=(owner,account)or previous[2]!=rel._digest(owner,0x41c,payload)or rel.snapshot(db,owner,account)is not None:raise ValueError('Farewell replay meets another pair or identity')
   answer=encode(True);guard(db)
   for event in answer:encode_event(event)
   return answer
 actual=quote(db,owner,account)
 if actual!=expected:raise ValueError('Farewell quote belongs to another pair generation')
 from els_server.storage.inventory_state import load_items
 def economic():
  return([load_items(db,uid)for uid in(owner,actual['peer_uid'])],db.execute('SELECT *FROM reward_balances WHERE uid IN(?,?)ORDER BY uid',(owner,actual['peer_uid'])).fetchall())
 economy=economic()
 stamp=rel._clock(now)
 if stamp<actual['created_at']:raise ValueError('Farewell precedes true pairing')
 pair=pair_row(db,actual['pair_id']);old_pairs=db.execute('SELECT *FROM native_couple_pairs_v1 ORDER BY id').fetchall();old_actions=db.execute('SELECT *FROM native_couple_actions_v1 ORDER BY operation').fetchall()
 initialize(db)
 db.execute('INSERT INTO native_couple_closures_v1 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)',(actual['pair_id'],operation,rel._digest(owner,0x41c,payload),owner,account,actual['peer_uid'],actual['peer_account'],stamp,0,0,receipt_before(pair,owner,account),receipt_after(actual['pair_id']),payload,POLICY))
 if db.execute('DELETE FROM native_couple_members_v1 WHERE pair_id=?',(actual['pair_id'],)).rowcount!=2:raise ValueError('Farewell exactly two active members')
 if rel.snapshot(db,owner,account)is not None or rel.snapshot(db,actual['peer_uid'],actual['peer_account'])is not None:raise ValueError('Farewell both cold projections must be solo')
 answer=encode(False)
 for event in answer:encode_event(event)
 guard(db);rel._write_guard(db)
 if db.execute('SELECT *FROM native_couple_pairs_v1 ORDER BY id').fetchall()!=old_pairs or db.execute('SELECT *FROM native_couple_actions_v1 ORDER BY operation').fetchall()!=old_actions:raise ValueError('Farewell altered immutable pairing/debit source')
 if economic()!=economy:raise ValueError('Farewell must preserve all owned UID inventory and ED')
 if checked(db,db.execute('SELECT *FROM native_couple_closures_v1 WHERE operation=?',(operation,)).fetchone())!=pair[0]:raise ValueError('Farewell final closure receipt')
 return answer
