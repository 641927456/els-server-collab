"""Atomic original couple proposal/answer, immutable debit source and cold view."""
import hashlib,json,sqlite3,time
from els_server.domain.relationship_rules import RING,eligible
from els_server.protocol.relationship_messages import propose_request,answer_request
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
TABLES=('native_couple_pairs_v1','native_couple_members_v1','native_couple_pending_v1','native_couple_actions_v1')
SCHEMAS={'native_couple_pairs_v1': 'CREATE TABLE native_couple_pairs_v1(id TEXT PRIMARY KEY,a INTEGER NOT NULL,b INTEGER NOT NULL,a_account INTEGER NOT NULL,b_account INTEGER NOT NULL,created_at INTEGER NOT NULL,proposal TEXT NOT NULL,acceptance TEXT NOT NULL,item_uid INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1))', 'native_couple_members_v1': 'CREATE TABLE native_couple_members_v1(owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,pair_id TEXT NOT NULL REFERENCES native_couple_pairs_v1(id))', 'native_couple_pending_v1': 'CREATE TABLE native_couple_pending_v1(operation TEXT PRIMARY KEY,proposer INTEGER NOT NULL UNIQUE,recipient INTEGER NOT NULL UNIQUE,proposer_account INTEGER NOT NULL,recipient_account INTEGER NOT NULL,proposer_session TEXT NOT NULL,recipient_session TEXT NOT NULL,item_uid INTEGER NOT NULL,item_json TEXT NOT NULL,created_at INTEGER NOT NULL,descriptor BLOB NOT NULL)', 'native_couple_actions_v1': 'CREATE TABLE native_couple_actions_v1(operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,kind INTEGER NOT NULL,owner INTEGER NOT NULL,peer INTEGER NOT NULL,payload BLOB NOT NULL,proposal TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL)'}
def _present(db):
 found=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE lower(name) IN (?,?,?,?)",TABLES))
 if found and found!=SCHEMAS:raise ValueError('Unknown or partial current couple schema')
 if db.execute("SELECT 1 FROM sqlite_master WHERE lower(tbl_name) IN (?,?,?,?) AND(type='trigger'OR(type='index'AND sql IS NOT NULL)) LIMIT 1",TABLES).fetchone():raise ValueError('Unreviewed couple schema extension')
 from els_server.storage.couple_closures import present
 present(db,base=bool(found))
 return bool(found)
def _schema(db):
 if _present(db):return
 if not db.in_transaction:raise ValueError('Couple schema outside writer transaction')
 for sql in SCHEMAS.values():db.execute(sql)
 _present(db)
def _write_guard(db):
 # Exactly the inventory and metadata tables touched by original remove().
 # Current native storage defines no triggers on these writer dependencies.
 tables=('inventory_items','equipment_attributes','equipment_durability','equipment_enhancement','item_expiration','item_locks','equipment_options','equipment_identification','equipment_enhancement_progress','item_seals','artifact_equipment_state','equipment_chip_tuning','equipment_reforge_states','equipment_engrave_previews','wardrobe_item_state','wardrobe_dyes')
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger'AND lower(tbl_name) IN("+','.join('?'for _ in tables)+') LIMIT 1',tables).fetchone():raise ValueError('Unreviewed couple inventory writer trigger')
 _present(db)
def _actor(db,uid,account):
 require_active_character(db,uid);require_owner(db,uid,account)
 row=db.execute('SELECT uid,name,unit_type FROM characters WHERE uid=?',(uid,)).fetchone()
 if row is None:raise ValueError('Couple missing saved character')
 return dict(zip(('uid','name','unit_type'),row))
def _digest(uid,kind,payload):return hashlib.sha256(str(uid).encode()+b':'+str(kind).encode()+b':'+payload).hexdigest()
def _debit(before,after,item_uid):
 if not isinstance(before,list)or not isinstance(after,list)or any(not isinstance(i,dict)for i in before+after):raise ValueError('Couple saved inventory receipt arrays')
 source=next((i for i in before if i['uid']==item_uid),None)
 if source is None or(source['template'],source['metadata'],source['group'])!=(RING,0,4)or source['count']<1:raise ValueError('Couple exact original ring source receipt')
 expected=[dict(i)for i in before]
 for i in expected:
  if i['uid']==item_uid:i['count']-=1
 expected=[i for i in expected if i['count']]
 if expected!=after:raise ValueError('Couple must debit exactly one bound ring')
 return source
def snapshot(db,owner,account):
 if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account,):raise ValueError('Couple cold owner')
 if not _present(db):return None
 from els_server.storage.couple_closures import closed_pairs
 closed=closed_pairs(db,owner,account)
 row=db.execute('SELECT pair_id,account_id FROM native_couple_members_v1 WHERE owner=?',(owner,)).fetchone()
 # Every generation involving this owner must retain its validated immutable
 # source, including old closures while a later pair is active.
 pairs={v[0]for v in db.execute('SELECT id FROM native_couple_pairs_v1 WHERE a=?OR b=?',(owner,owner))}
 if pairs!=closed|({row[0]}if row is not None else set()):raise ValueError('Couple pair lacks member or exact closure')
 if row is None:return None
 if row[1]!=account or row[0]in closed:raise ValueError('Couple member account or closed generation')
 return _pair_snapshot(db,row[0],owner,account)

def _pair_snapshot(db,pair_id,owner,account,*,closed=False):
 pair=db.execute('SELECT a,b,a_account,b_account,created_at,proposal,acceptance,item_uid,version FROM native_couple_pairs_v1 WHERE id=?',(pair_id,)).fetchone()
 if pair is None or pair[-1]!=1:raise ValueError('Unknown couple member/pair')
 a,b,aa,ba,stamp,proposal,acceptance,item_uid,version=pair
 if(owner,account)not in((a,aa),(b,ba)):raise ValueError('Couple exact pair owner/account')
 members=db.execute('SELECT owner,account_id FROM native_couple_members_v1 WHERE pair_id=? ORDER BY owner',(pair_id,)).fetchall()
 if members!=([]if closed else sorted([(a,aa),(b,ba)]))or a==b or owner not in(a,b)or stamp<=0:raise ValueError('Couple exactly two reciprocal owned members')
 for uid,aid in sorted([(a,aa),(b,ba)]):
  if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(aid,):raise ValueError('Couple member account changed')
 action=db.execute('SELECT request_hash,kind,owner,peer,payload,proposal,status,created_at,before_json,after_json FROM native_couple_actions_v1 WHERE operation=?',(acceptance,)).fetchone()
 if action is None or action[1:4]!=(0x3fe,b,a)or action[5:8]!=(proposal,'accepted',stamp)or action[0]!=_digest(b,0x3fe,action[4]):raise ValueError('Couple lacks immutable exact acceptance producer')
 parsed=answer_request(action[4])
 if(parsed['answer'],parsed['proposer'],parsed['recipient'])!=(0,a,b):raise ValueError('Couple mutual acceptance source identities')
 source=_debit(json.loads(action[8]),json.loads(action[9]),item_uid)
 proposed=db.execute('SELECT kind,owner,peer,payload,status,request_hash,before_json,after_json FROM native_couple_actions_v1 WHERE operation=?',(proposal,)).fetchone()
 if proposed is None or proposed[:3]!=(0x3fb,a,b)or proposed[4]!='proposed'or proposed[5]!=_digest(a,0x3fb,proposed[3]):raise ValueError('Couple lacks original proposal')
 if propose_request(proposed[3])!=parsed['own_name']or json.loads(proposed[6])!=[source]or proposed[6]!=proposed[7]:raise ValueError('Couple exact proposal ring source changed')
 peer=b if owner==a else a;name=db.execute('SELECT name FROM characters WHERE uid=?',(peer,)).fetchone()
 if name is None:raise ValueError('Couple partner character unavailable')
 return dict(pair_id=pair_id,kind=1,peer_uid=peer,peer_name=name[0],created_at=stamp)
def _ring(db,owner,*,now,uid=None):
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 candidates=[i for i in load_items(db,owner)if(i['template'],i['metadata'],i['group'])==(RING,0,4)and(uid is None or i['uid']==uid)]
 for item in sorted(candidates,key=lambda i:(i['slot'],i['uid'])):
  try:
   require_current(item,now=now);require_unlocked(item,now=now)
   if item.get('sealed',False)or item.get('seal_count',0):continue
   return item
  except ValueError:continue
 raise ValueError('Couple needs a current unlocked owned269710')
def _clock(now):
 now=int(time.time())if now is None else now
 if type(now)is not int or not 0<now<2**63:raise ValueError('Couple server clock')
 return now
def _previous(db,operation,owner,peer,kind,payload):
 if type(operation)is not str or not 1<=len(operation)<=160:raise ValueError('Couple operation identity')
 row=db.execute('SELECT request_hash,owner,peer,kind,status,proposal FROM native_couple_actions_v1 WHERE operation=?',(operation,)).fetchone()
 if row is not None and row[:4]!=(_digest(owner,kind,payload),owner,peer,kind):raise ValueError('Conflicting couple replay')
 return row
def propose(db,owner,account,target,target_account,session,target_session,payload,operation,*,guard,encode,now=None):
 now=_clock(now);_write_guard(db);guard(db);a=_actor(db,owner,account);b=_actor(db,target,target_account);eligible(a,b)
 if propose_request(payload)!=b['name']:raise ValueError('Couple exact online target nickname')
 if snapshot(db,owner,account)is not None or snapshot(db,target,target_account)is not None:raise ValueError('Couple actors must both be solo')
 _schema(db);old=_previous(db,operation,owner,target,0x3fb,payload)
 if old is None:
  ring=_ring(db,owner,now=now)
  pending=db.execute('SELECT operation,proposer,recipient,proposer_session,recipient_session,created_at FROM native_couple_pending_v1 WHERE proposer IN(?,?)OR recipient IN(?,?)',(owner,target,owner,target)).fetchall()
  for op,p,t,ps,ts,created in pending:
   current={owner:session,target:target_session}
   if now>created+10 or any(uid in current and current[uid]!=sid for uid,sid in((p,ps),(t,ts))):db.execute('DELETE FROM native_couple_pending_v1 WHERE operation=?',(op,))
   else:raise ValueError('Couple current pending invitation exists')
  db.execute('INSERT INTO native_couple_pending_v1 VALUES(?,?,?,?,?,?,?,?,?,?,?)',(operation,owner,target,account,target_account,session,target_session,ring['uid'],json.dumps(ring,sort_keys=True),now,payload))
  original_ring=json.dumps([ring],sort_keys=True)
  db.execute('INSERT INTO native_couple_actions_v1 VALUES(?,?,?,?,?,?,?,?,?,?,?)',(operation,_digest(owner,0x3fb,payload),0x3fb,owner,target,payload,operation,'proposed',now,original_ring,original_ring))
 else:
  if old[4:]!=('proposed',operation):raise ValueError('Couple proposal receipt state')
  ring=_ring(db,owner,now=now)
 row=db.execute('SELECT proposer_session,recipient_session,created_at,item_uid,descriptor FROM native_couple_pending_v1 WHERE operation=?',(operation,)).fetchone()
 if row is None or row[:2]!=(session,target_session)or row[3:]!=(ring['uid'],payload)or now>row[2]+10:raise ValueError('Couple expired or changed proposal')
 events=encode(a,b,False,())
 for e in events:encode_event(e)
 guard(db)
 _write_guard(db)
 if _actor(db,owner,account)!=a or _actor(db,target,target_account)!=b:raise ValueError('Couple late identity changed')
 return events
def answer(db,owner,account,peer,peer_account,session,peer_session,payload,operation,*,guard,encode,now=None):
 now=_clock(now);_write_guard(db);parsed=answer_request(payload);guard(db);target=_actor(db,owner,account);proposer=_actor(db,peer,peer_account);eligible(proposer,target)
 if(parsed['proposer'],parsed['recipient'],parsed['name'],parsed['own_name'])!=(peer,owner,proposer['name'],target['name']):raise ValueError('Couple exact original answer identities')
 if not _present(db):raise ValueError('Couple missing original proposal schema')
 old=_previous(db,operation,owner,peer,0x3fe,payload)
 if old is not None:
  saved=snapshot(db,owner,account)
  if old[4]=='accepted'and saved is not None and saved['pair_id']==operation and saved['peer_uid']==peer:
   events=encode(proposer,target,True,());guard(db);return events
  if old[4]=='rejected':events=encode(proposer,target,True,());guard(db);return events
  raise ValueError('Couple unknown answer receipt')
 if snapshot(db,owner,account)is not None or snapshot(db,peer,peer_account)is not None:raise ValueError('Couple answer after relation changed')
 row=db.execute('SELECT operation,proposer_account,recipient_account,proposer_session,recipient_session,item_uid,item_json,created_at,descriptor FROM native_couple_pending_v1 WHERE proposer=?AND recipient=?',(peer,owner)).fetchone()
 if row is None or row[1:5]!=(peer_account,account,peer_session,session)or now>row[7]+10 or row[8]!=__import__('els_server.protocol.relationship_messages',fromlist=['descriptor']).descriptor(target['name']):raise ValueError('Couple pending source/session/deadline')
 source=db.execute('SELECT before_json,after_json,payload,kind,owner,peer,status,request_hash FROM native_couple_actions_v1 WHERE operation=?',(row[0],)).fetchone()
 if(source is None or source[0]!=source[1]or json.loads(source[0])!=[json.loads(row[6])]or source[2]!=row[8]
    or source[3:7]!=(0x3fb,peer,owner,'proposed')or source[7]!=_digest(peer,0x3fb,source[2])):raise ValueError('Couple pending lacks exact immutable proposal ring producer')
 before=load_items(db,peer);changes=[];status='rejected'
 if parsed['answer']==0:
  ring=_ring(db,peer,now=now,uid=row[5])
  if ring!=json.loads(row[6]):raise ValueError('Couple proposal-bound ring changed')
  if ring['count']==1:remove(db,peer,ring)
  elif db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=?AND uid=?AND count=?',(peer,ring['uid'],ring['count'])).rowcount!=1:raise ValueError('Couple ring debit changed')
  after=load_items(db,peer);_debit(before,after,ring['uid']);position=(ring['group'],ring['slot']);changes=[(position,next((i for i in after if(i['group'],i['slot'])==position),None))];status='accepted'
  db.execute('INSERT INTO native_couple_pairs_v1 VALUES(?,?,?,?,?,?,?,?,?,1)',(operation,peer,owner,peer_account,account,now,row[0],operation,ring['uid']))
  db.executemany('INSERT INTO native_couple_members_v1 VALUES(?,?,?)',((peer,peer_account,operation),(owner,account,operation)))
 else:after=before
 db.execute('INSERT INTO native_couple_actions_v1 VALUES(?,?,?,?,?,?,?,?,?,?,?)',(operation,_digest(owner,0x3fe,payload),0x3fe,owner,peer,payload,row[0],status,now,json.dumps(before,sort_keys=True),json.dumps(after,sort_keys=True)))
 db.execute('DELETE FROM native_couple_pending_v1 WHERE operation=?',(row[0],))
 events=encode(proposer,target,False,changes)
 for e in events:encode_event(e)
 guard(db)
 if parsed['answer']==0:
  if load_items(db,peer)!=after:raise ValueError('Couple inventory changed after exact debit receipt')
  _debit(before,load_items(db,peer),row[5])
  if snapshot(db,owner,account)['peer_uid']!=peer or snapshot(db,peer,peer_account)['peer_uid']!=owner:raise ValueError('Couple reciprocal cold source changed')
 _write_guard(db)
 if _actor(db,owner,account)!=target or _actor(db,peer,peer_account)!=proposer:raise ValueError('Couple late saved character changed')
 return events
