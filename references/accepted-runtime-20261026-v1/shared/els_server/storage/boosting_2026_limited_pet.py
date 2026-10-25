"""Owned Dana90 activation, immutable deadline and one-shot active expiry stop."""
import hashlib,sqlite3,struct
from contextlib import closing
from time import time as _time
from els_server.domain.boosting_2026_limited_pet import TEMPLATE,UNIT,DAYS,definition,enabled
from els_server.protocol import companion_messages as wire
from els_server.protocol.protocol_codec import encode_event
TABLE='activity2026_limited_pets'
class ExpiredLimitedPet(ValueError):pass
def epoch():return int(_time())
def now(value=None):
 value=epoch() if value is None else value
 if type(value) is not int or not 0<=value<2**40-DAYS*86400:raise ValueError('Limited Dana epoch')
 return value
def present(db,name=TABLE):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None
def ensure(db):
 if not db.in_transaction:raise ValueError('Limited Dana requires transaction')
 db.execute('''CREATE TABLE IF NOT EXISTS activity2026_limited_pets (
 pet INTEGER PRIMARY KEY REFERENCES companions(uid),owner INTEGER NOT NULL REFERENCES characters(uid),
 source_uid INTEGER NOT NULL,source_group INTEGER NOT NULL CHECK(source_group=4),source_slot INTEGER NOT NULL CHECK(source_slot>=0),
 operation TEXT NOT NULL,activated_at INTEGER NOT NULL CHECK(activated_at>=0),expires_at INTEGER NOT NULL CHECK(expires_at>activated_at),
 needs_stop INTEGER NOT NULL DEFAULT 0 CHECK(needs_stop IN (0,1)),UNIQUE(owner,operation))''')
def attach(db,owner,pets):
 if not present(db):return
 definition();saved={r[0]:r for r in db.execute('SELECT pet,owner,source_uid,activated_at,expires_at FROM '+TABLE+' WHERE owner=?',(owner,))}
 for p in pets:
  if p['uid'] not in saved:continue
  uid,subject,source,start,end=saved[p['uid']]
  if (p['kind'],p['unit'],p['owner'],p['source_item'])!=('pet',UNIT,subject,source) or end!=start+DAYS*86400 or subject!=owner:raise ValueError('Limited Dana saved identity/deadline')
  p['expires_at']=end
def require_current(pet,*,at=None):
 end=pet.get('expires_at',0)
 if type(end) is not int or end<0:raise ValueError('Invalid companion deadline')
 if end and now(at)>=end:raise ExpiredLimitedPet('Limited pet expired')
def clear_pending(db,owner):
 if present(db):db.execute('UPDATE '+TABLE+' SET needs_stop=0 WHERE owner=? AND needs_stop<>0',(owner,))
def expire_active(db,owner,*,at=None):
 if not present(db):return False
 value=now(at);row=db.execute('SELECT a.pet,p.expires_at FROM companion_active a JOIN '+TABLE+' p ON p.pet=a.pet AND p.owner=a.owner WHERE a.owner=?',(owner,)).fetchone()
 if row is None or value<row[1]:return False
 db.execute('UPDATE companion_active SET pet=0 WHERE owner=? AND pet=?',(owner,row[0]))
 db.execute('UPDATE '+TABLE+' SET needs_stop=1 WHERE pet=? AND owner=?',(row[0],owner))
 if present(db,'pet_growth_clocks'):db.execute('DELETE FROM pet_growth_clocks WHERE owner=? AND pet=?',(owner,row[0]))
 return True
def periodic(path,owner,*,at=None):
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  if not present(db):return []
  value=now(at)
  # Owners with no pending stop or due active pet remain read-only. The
  # writer rechecks after BEGIN so a later summon cannot be stopped by stale
  # eligibility, while current-use guards reject expired pets immediately.
  due=db.execute('SELECT 1 FROM '+TABLE+' p LEFT JOIN companion_active a ON a.owner=p.owner AND a.pet=p.pet WHERE p.owner=? AND (p.needs_stop=1 OR (a.pet=p.pet AND p.expires_at<=?)) LIMIT 1',(owner,value)).fetchone()
  if due is None:return []
  db.execute('BEGIN IMMEDIATE');expire_active(db,owner,at=value)
  if not db.execute('SELECT 1 FROM '+TABLE+' WHERE owner=? AND needs_stop=1',(owner,)).fetchone():return []
  active=db.execute('SELECT pet FROM companion_active WHERE owner=?',(owner,)).fetchone()
  result=[] if active and active[0] else [wire.pet_summon(0)]
  for event in result:encode_event(event)
  clear_pending(db,owner);return result
def reconcile_summon(db,owner,payload):
 # Scope receipt reconciliation to owners who have this finite lifecycle.
 if not present(db) or not db.execute('SELECT 1 FROM '+TABLE+' WHERE owner=?',(owner,)).fetchone():return None
 from els_server.storage.companion_state import rows
 pets=rows(db,owner,'pet');requested=wire.uid_request(payload,zero=True)
 if requested:
  old=next((p for p in pets if p['uid']==requested),None)
  if old is None:raise ValueError('Summon retry owner missing')
  require_current(old)
 active=db.execute('SELECT pet FROM companion_active WHERE owner=?',(owner,)).fetchone();uid=active[0] if active else 0
 current=next((p for p in pets if p['uid']==uid),None)
 if uid and current is None:raise ValueError('Active summon retry owner missing')
 if current:require_current(current)
 result=wire.pet_summon(0,current);encode_event(result);return result
def _delta(db,owner,row):
 from els_server.storage.inventory_state import load_items
 pet,subject,source,group,slot,op,start,end,pending=row
 current=next((i for i in load_items(db,owner) if (i['group'],i['slot'])==(group,slot)),None)
 return wire.inventory_delta([current]) if current else wire.inventory_delta(removed=dict(uid=source,template=TEMPLATE,metadata=0,count=1,group=group,slot=slot))
def activate(path,owner,payload,operation,*,at=None,account_id=None):
 if not enabled():return None
 if not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('Limited pet operation identity')
 item_uid,name=wire.create_pet_request(payload);digest=hashlib.sha256((0x2e8).to_bytes(4,'big')+payload).hexdigest();value=now(at)
 from els_server.storage.companion_state import ensure as companions,rows
 from els_server.storage.inventory_state import load_items
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  from els_server.storage.item_actor import require_active_character
  require_active_character(db,owner)
  if account_id is not None:
   from els_server.storage.profession_state import require_owner
   require_owner(db,owner,account_id)
  saved=db.execute('SELECT * FROM '+TABLE+' WHERE owner=? AND operation=?',(owner,operation)).fetchone() if present(db) else None
  if saved:
   receipt=db.execute('SELECT digest,kind FROM companion_receipts WHERE owner=? AND operation=?',(owner,operation)).fetchone()
   if receipt!=(digest,0x2e9):raise ValueError('Conflicting or missing limited pet receipt')
   pet=next((p for p in rows(db,owner,'pet') if p['uid']==saved[0]),None)
   if pet is None or pet['name']!=name or pet['source_item']!=item_uid:raise ValueError('Limited pet receipt identity')
   result=wire.activation_ack('pet',-1) if value>=pet['expires_at'] else wire.activation_ack('pet',0,pet,_delta(db,owner,saved))
   encode_event(result);return result
  source=next((i for i in load_items(db,owner) if i['uid']==item_uid),None)
  if source is None or source['template']!=TEMPLATE:return None
  if source['group']!=4:raise ValueError('Owned Dana item outside native bag')
  definition()
  from els_server.domain.item_expiration import require_current as current_item
  from els_server.domain.item_locks import require_unlocked
  current_item(source,now=value);require_unlocked(source,now=value)
  companions(db)
  if db.execute('SELECT 1 FROM companion_receipts WHERE owner=? AND operation=?',(owner,operation)).fetchone():raise ValueError('Conflicting limited pet operation')
  if db.execute("SELECT 1 FROM companions WHERE owner=? AND kind='pet' AND name=?",(owner,name)).fetchone() or len(rows(db,owner,'pet'))>=1000:raise ValueError('Pet name/capacity conflict')
  revision=db.execute('SELECT revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
  if revision is None or type(revision[0])is not int or revision[0]>=2**63-1:raise ValueError('Limited pet revision bound')
  uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
  if not 0<uid<2**63-1:raise ValueError('Limited pet UID limit')
  end=value+DAYS*86400;pet=dict(uid=uid,owner=owner,kind='pet',unit=UNIT,name=name,source_item=item_uid,expires_at=end,pickup=True)
  ensure(db);db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,));db.execute('INSERT INTO companions VALUES (?,?,?,?,?,?)',tuple(pet[k] for k in ('uid','owner','kind','unit','name','source_item')))
  db.execute('INSERT INTO '+TABLE+' VALUES (?,?,?,?,?,?,?,?,0)',(uid,owner,item_uid,source['group'],source['slot'],operation,value,end))
  from els_server.storage.pet_progression import DEFAULT,save
  pet.update(DEFAULT);save(db,owner,pet)
  from els_server.storage.pet_support import ensure as support
  support(db);db.execute('INSERT INTO pet_entitlements VALUES (?,?,1)',(owner,uid))
  if source['count']==1:
   from els_server.storage.item_instances import remove
   remove(db,owner,source);delta=wire.inventory_delta(removed=source)
  else:
   db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,owner));delta=wire.inventory_delta([dict(source,count=source['count']-1)])
  result=wire.activation_ack('pet',0,pet,delta);encode_event(result)
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
  db.execute('INSERT INTO companion_receipts VALUES (?,?,?,?,?)',(owner,operation,digest,result.kind,result.payload))
  return result
