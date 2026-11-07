"""Consume one owned native box through the original inventory factory/receipt."""
from contextlib import closing
from pathlib import Path
import secrets,sqlite3,struct
from els_server.domain import black_market_box_rules as rules
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances

def perform(path,owner,account_id,template,payload,operation,authorize,randbelow=secrets.randbelow,encode=result):
 value=use_request(payload)
 if any(v not in(0,1)for v in(value.flag1,value.flag2,value.flag3)):raise ValueError('Market box native flags')
 rules.entry(template);owner,digest=_identity(owner,0x196,struct.pack('>Qi',account_id,template)+payload,operation)
 def guard(db):
  if authorize()is not True or not db.in_transaction:raise ValueError('Market box stale selected actor')
  require_active_character(db,owner)
  if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account_id,):raise ValueError('Market box foreign account')
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
  before=load_items(db,owner);balance=balances(db,owner);old=_previous(db,operation,digest)
  if old is not None:
   reply=encode(balance['ed'],current_changes(db,operation,owner,0x196,old,before))
   for e in reply:encode_event(e)
   guard(db);return reply
  item=next((i for i in before if i['uid']==value.uid),None)
  if item is None or item['template']!=template or item['group']!=4 or item.get('sealed'):raise ValueError('Owned usable market box required')
  require_current(item);require_unlocked(item)
  if balance['revision']>=2**63-1:raise ValueError('Market box revision bound')
  plan,options=rules.plan(template,value.choices,value.option,randbelow)
  if item['count']==1:remove(db,owner,item)
  elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',(item['uid'],owner,item['count'])).rowcount!=1:raise ValueError('Market box source changed')
  source=rules.issue_source(db,owner,account_id,item,plan,options,authorize)
  grants=grant_items(db,plan,owner,black_market_box_source=source)
  after=load_items(db,owner);positions=list(dict.fromkeys([(item['group'],item['slot']),*[(i['group'],i['slot'])for i in grants]]));current={(i['group'],i['slot']):i for i in after}
  reply=encode(balance['ed'],[(p,current.get(p))for p in positions],[(p['template'],p['quantity'])for p in plan])
  for e in reply:encode_event(e)
  guard(db)
  if db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=? AND revision=?',(owner,balance['revision'])).rowcount!=1:raise ValueError('Market box balance changed')
  _commit(db,operation,digest,owner,0x196,positions,before,after);guard(db);return reply
