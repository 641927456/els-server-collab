"""Account-wide signed64 ERP and independently deduplicated source receipts."""
import hashlib,json,sqlite3,time
from contextlib import closing
from els_server.domain.resonance import curve,level,limit

def owner(db,uid,expected=None):
 row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
 if row is None or type(row[0]) is not int or row[0]<1 or (expected is not None and row[0]!=expected):raise ValueError('ERP character/account ownership')
 return row[0]

def ensure(db):
 if not db.in_transaction:raise ValueError('ERP schema requires caller transaction')
 db.execute('CREATE TABLE IF NOT EXISTS account_resonance (account_id INTEGER PRIMARY KEY CHECK(account_id>0), enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), experience INTEGER NOT NULL CHECK(experience>=0), revision INTEGER NOT NULL CHECK(revision>=0))')
 db.execute('CREATE TABLE IF NOT EXISTS resonance_award_receipts (operation_id TEXT PRIMARY KEY, account_id INTEGER NOT NULL, owner INTEGER NOT NULL, source TEXT NOT NULL, proof_sha256 TEXT NOT NULL, requested INTEGER NOT NULL, effective INTEGER NOT NULL, before_exp INTEGER NOT NULL, after_exp INTEGER NOT NULL)')

def snapshot(db,uid,account_id=None):
 account=owner(db,uid,account_id);row=None
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_resonance'").fetchone():row=db.execute('SELECT enabled,experience,revision FROM account_resonance WHERE account_id=?',(account,)).fetchone()
 if row is None:return dict(account_id=account,enabled=False,experience=0,level=0,auxiliary=0,revision=0)
 enabled,xp,revision=row
 if type(enabled) is not int or enabled not in (0,1) or type(xp) is not int or not 0<=xp<=limit() or type(revision) is not int or revision<0 or (not enabled and xp):raise ValueError('Invalid saved ERP state')
 return dict(account_id=account,enabled=bool(enabled),experience=xp,level=level(xp) if enabled else 0,auxiliary=0,revision=revision)

def state(path,uid,account_id=None):
 with closing(sqlite3.connect(path,timeout=10)) as db:return snapshot(db,uid,account_id)

def route(db,uid,account_id=None):
 account=owner(db,uid,account_id)
 row=db.execute('SELECT c.level,b.experience FROM characters c JOIN reward_balances b ON b.uid=c.uid WHERE c.uid=?',(uid,)).fetchone()
 if row is None:raise ValueError('ERP character/balance missing')
 from els_server.game_data import client_data
 if row[0]<99:return 'ordinary'
 return 'resonance' if row[1]>=client_data().thresholds[-1] and snapshot(db,uid,account)['enabled'] else 'blocked'

def receipt(db,operation):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='resonance_award_receipts' AND type='table'").fetchone():return None
 row=db.execute('SELECT account_id,owner,source,proof_sha256,requested,effective,before_exp,after_exp FROM resonance_award_receipts WHERE operation_id=?',(operation,)).fetchone()
 return dict(zip(('account_id','owner','source','proof_sha256','requested','effective','before','after'),row)) if row else None

def award(db,uid,operation,proof,source,requested,account_id=None):
 if not db.in_transaction or source not in ('kill','clear') or not isinstance(proof,bytes) or not proof or type(requested) is not int or not 0<=requested<2**63:raise ValueError('ERP source transaction/bounds')
 account=owner(db,uid,account_id);digest=hashlib.sha256(proof).hexdigest();prior=receipt(db,operation)
 if prior:
  if any(prior[k]!=v for k,v in dict(account_id=account,owner=uid,source=source,proof_sha256=digest,requested=requested).items()):raise ValueError('Conflicting ERP source receipt')
  return dict(prior,replayed=True)
 if route(db,uid,account)!='resonance':raise ValueError('ERP award requires already unlocked full-level owner')
 before=snapshot(db,uid,account);amount=min(requested,limit()-before['experience']);after=before['experience']+amount
 ensure(db)
 db.execute('UPDATE account_resonance SET experience=?,revision=revision+1 WHERE account_id=?',(after,account))
 db.execute('INSERT INTO resonance_award_receipts VALUES (?,?,?,?,?,?,?,?,?)',(operation,account,uid,source,digest,requested,amount,before['experience'],after))
 return dict(account_id=account,owner=uid,source=source,proof_sha256=digest,requested=requested,effective=amount,before=before['experience'],after=after,replayed=False)

def book_templates():
 # Existing owned current-client books only. No new shop/drop/source is opened.
 from els_server.domain.resonance import book_definitions
 return {r['template']:r for r in book_definitions()}

def use_book(path,uid,account_id,payload,operation,*,prepare=None):
 from els_server.protocol.career_messages import use_request,use_ack
 from els_server.storage.inventory_state import load_items
 item_uid=use_request(payload)
 if not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('ERP activation operation')
 proof=hashlib.sha256(str((account_id,uid)).encode()+payload).hexdigest()
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('BEGIN IMMEDIATE');owner(db,uid,account_id)
  from els_server.storage.item_actor import require_active_character
  from els_server.protocol.protocol_codec import encode_event
  if db.execute("SELECT 1 FROM sqlite_master WHERE name='resonance_book_receipts' AND type='table'").fetchone():
   old=db.execute('SELECT proof_sha256,bag_group,slot FROM resonance_book_receipts WHERE operation_id=?',(operation,)).fetchone()
   if old:
    if old[0]!=proof:raise ValueError('Conflicting ERP activation retry')
    require_active_character(db,uid)
    if prepare is not None:prepare()
    current=next((i for i in load_items(db,uid) if (i['group'],i['slot'])==old[1:]),None)
    ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
    event=use_ack([(old[1:],current)],ed=ed);encode_event(event)
    if prepare is not None:prepare()
    require_active_character(db,uid)
    return dict(replayed=True,events=[event])
  item=next((x for x in load_items(db,uid) if x['uid']==item_uid),None)
  if item is None or item['template'] not in book_templates():return None
  require_active_character(db,uid)
  if prepare is not None:prepare()
  if item['group']!=4 or item.get('lock_until',0)>time.time() or item.get('sealed',False):raise ValueError('ERP book not usable in current owned slot')
  from els_server.domain.item_expiration import require_current
  require_current(item)
  if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('ERP book requires level99')
  if snapshot(db,uid,account_id)['enabled']:raise ValueError('ERP already active for this account')
  remaining=dict(item,count=item['count']-1) if item['count']>1 else None
  ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
  event=use_ack([((item['group'],item['slot']),remaining)],item['template'],ed)
  encode_event(event)
  ensure(db);db.execute('INSERT INTO account_resonance VALUES (?,1,0,1) ON CONFLICT(account_id) DO UPDATE SET enabled=1,revision=account_resonance.revision+1',(account_id,))
  if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,uid))
  else:
   from els_server.storage.item_expiration import forget
   forget(db,item_uid);db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,uid))
  db.execute('CREATE TABLE IF NOT EXISTS resonance_book_receipts (operation_id TEXT PRIMARY KEY, proof_sha256 TEXT NOT NULL, owner INTEGER NOT NULL, item_uid INTEGER NOT NULL, bag_group INTEGER NOT NULL, slot INTEGER NOT NULL)')
  db.execute('INSERT INTO resonance_book_receipts VALUES (?,?,?,?,?,?)',(operation,proof,uid,item_uid,item['group'],item['slot']))
  if prepare is not None:prepare()
  require_active_character(db,uid)
  return dict(replayed=False,events=[event])

