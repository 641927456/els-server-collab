"""Exact native Feta source debit, original factory, full reply and one receipt."""
from pathlib import Path
from contextlib import closing
import json,sqlite3,struct,time
from els_server.domain.feta_exchange_rules import request,plain_source,_FetaAuthority,SOURCE
from els_server.storage.cartridge_exchange import _context as original_context
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import remove
from els_server.domain.manufacture_requirements import inventory_candidates
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances
from els_server.protocol.feta_exchange_messages import acknowledgement
from els_server.protocol.protocol_codec import Event,encode_event

WRITER_ENABLED=True

def _context(db,owner,account,authority):
 if(not WRITER_ENABLED or type(authority)is not _FetaAuthority or authority.owner!=owner
    or authority.account_id!=account or not db.in_transaction
    or db.execute('PRAGMA foreign_keys').fetchone()!=(1,)):raise ValueError('Feta exact writer authority')
 files=db.execute('PRAGMA database_list').fetchall()
 if len(files)!=1 or files[0][1]!='main' or Path(files[0][2]).resolve()!=authority.path:raise ValueError('Feta exact original SQL store')
 original_context(db,owner,account,authority);require_active_character(db,owner)

def _transition(before,after,positions,row):
 from els_server.domain.inventory_items import validate_item
 if type(before)is not list or type(after)is not list:raise ValueError('Feta receipt arrays')
 for items in(before,after):
  for item in items:validate_item(item)
 b,a={i['uid']:i for i in before},{i['uid']:i for i in after}
 if len(b)!=len(before)or len(a)!=len(after):raise ValueError('Feta duplicate historical UID')
 used=gained=0;changed=[]
 for uid in b.keys()|a.keys():
  old,new=b.get(uid),a.get(uid)
  if old==new:continue
  if old is not None and old['template']==row['source']:
   if not plain_source(old,row['source'])or new is not None and({k:v for k,v in old.items()if k!='count'}!={k:v for k,v in new.items()if k!='count'}or new['count']>=old['count']):raise ValueError('Feta historical material mutation')
   used+=old['count']-(new['count']if new else 0);changed.append((old['group'],old['slot']))
  elif new is not None and new['template']==row['destination']:
   if old is not None:
    if {k:v for k,v in old.items()if k!='count'}!={k:v for k,v in new.items()if k!='count'}or new['count']<=old['count']:raise ValueError('Feta historical product merge')
   elif set(new)!={'uid','template','metadata','count','group','slot'}:raise ValueError('Feta original plain product')
   gained+=new['count']-(old['count']if old else 0);changed.append((new['group'],new['slot']))
  else:raise ValueError('Feta changed unrelated inventory')
 if used!=row['source_quantity']or gained!=row['destination_quantity'] or len(set(positions))!=len(positions)or set(positions)!=set(changed):raise ValueError('Feta exact historical debit/product/positions')

def _history(db,owner,operation,positions,row):
 r=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
 if r is None or r[:2]!=(owner,0x223):raise ValueError('Feta paired receipt owner/kind')
 try:_transition(json.loads(r[2]),json.loads(r[3]),positions,row)
 except(KeyError,TypeError,json.JSONDecodeError)as e:raise ValueError('Feta corrupt receipt')from e

def exchange(path,owner,payload,operation,*,account_id,authorize,now=None,encode=acknowledgement):
 row=request(payload)
 from els_server.storage import feta_exchange_weekly as weekly
 from els_server.protocol.feta_limit_messages import snapshot_event
 if(type(authorize)is not _FetaAuthority or authorize.operation!=operation or authorize.payload!=payload
    or type(account_id)is not int or not 1<=account_id<2**63):raise ValueError('Feta exact request authority')
 if now is not None and(type(now)is not int or not 0<=now<2**40):raise ValueError('Feta bounded original clock')
 owner,digest=_identity(owner,0x223,struct.pack('>iQ',1012,account_id)+payload,operation)
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');_context(db,owner,account_id,authorize)
  # Sample the production clock only once this request owns the write lock.
  # Waiting for another transaction must not preserve expired eligibility.
  if now is None:now=int(time.time())
  wallet=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone());before=load_items(db,owner);old=_previous(db,operation,digest)
  if old is not None:
   _history(db,owner,operation,old,row);weekly.receipt(db,account_id,owner,row,operation);changes=current_changes(db,operation,owner,0x223,old,before)
   events=[Event(0x201,kind=0x224,payload=encode(wallet['ed'],changes,[],exchange_type=row['type']))]
   if row['index']>=686:events.append(snapshot_event(db,account_id,now))
   for e in events:encode_event(e)
   _context(db,owner,account_id,authorize);return events
  if row['index']>=686:weekly.reserve(db,account_id,owner,row,operation,now)
  cap=None
  if row['index']in(689,690):
   from els_server.storage.feta_exchange_source import _FetaSource
   cap=_FetaSource(db,owner,account_id,authorize,operation,payload)
  by_uid={i['uid']:i for i in before};candidates=[(u,c)for u,c in inventory_candidates(before,now=now).get(row['source'],())if plain_source(by_uid[u],row['source'])]
  need=row['source_quantity']
  if sum(c for u,c in candidates)<need:raise ValueError('Feta insufficient eligible plain fragments')
  positions=[];debits=[]
  for uid,count in sorted(candidates,key=lambda p:(by_uid[p[0]]['group'],by_uid[p[0]]['slot'],p[0])):
   if not need:break
   item=by_uid[uid];take=min(need,count);need-=take;debits.append((uid,take));positions.append((item['group'],item['slot']))
   if take==count:remove(db,owner,item)
   elif db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=? AND count=?',(take,uid,owner,count)).rowcount!=1:raise ValueError('Feta source CAS')
  _context(db,owner,account_id,authorize)
  if cap is not None:cap.debit_complete(debits)
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
  t=row['destination'];plan=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=row['destination_quantity'])]
  if t in range(119217,119221):
   # The original manufacture factory allocates a real standalone prototype.
   # Never merge a metadata0 prototype merely because a legacy reader permits999.
   from els_server.storage.inventory_state import validate_plan
   from els_server.storage.manufacture import make_item
   from els_server.storage.item_instances import insert
   validate_plan(plan)
   product=make_item(db,owner,t,load_items(db,owner),randbelow=lambda n:(_ for _ in()).throw(ValueError('Prototype factory must not roll')))
   granted=[insert(db,owner,product)]
  else:granted=grant_items(db,plan,owner,feta_exchange_source=cap)
  if cap is not None:cap.close()
  if not granted or any(i['template']!=t for i in granted):raise ValueError('Feta original factory result')
  positions=list(dict.fromkeys(positions+[(i['group'],i['slot'])for i in granted]));after=load_items(db,owner);_transition(before,after,positions,row)
  current={(i['group'],i['slot']):i for i in after};events=[Event(0x201,kind=0x224,payload=encode(wallet['ed'],[(p,current.get(p))for p in positions],[(t,row['destination_quantity'])],exchange_type=row['type']))]
  if row['index']>=686:events.append(snapshot_event(db,account_id,now))
  for e in events:encode_event(e)
  if db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()!=tuple(wallet[k]for k in('ed','experience','revision')):raise ValueError('Feta zero-fee wallet preservation')
  _context(db,owner,account_id,authorize);_commit(db,operation,digest,owner,0x223,positions,before,after);_history(db,owner,operation,positions,row);weekly.receipt(db,account_id,owner,row,operation);_context(db,owner,account_id,authorize)
  return events
