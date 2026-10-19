"""Three Mirror conversion lines and 1+locked_count tickets commit exactly once."""
import sqlite3,secrets
from contextlib import closing
from els_server.domain.artifact_conversion import validate,draw
from els_server.domain.artifact_progression import catalog
from els_server.domain.item_expiration import require_current,expired
from els_server.domain.item_locks import require_unlocked,locked
from els_server.protocol.artifact_socket_messages import request,acknowledgement
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items
from els_server.storage.npc_trade import balances
from els_server.storage.equipment_options import replace
from els_server.storage.artifact_progression import consume
def perform(path,owner,payload,operation,randbelow=secrets.randbelow):
 uid,groups,profession,mode=request(payload)
 if mode!=20 or profession or set(groups)!={31}:raise ValueError('Unsupported Artifact conversion mode')
 locked_options=groups[31]
 if set(locked_options)-{0,1,2}:raise ValueError('Artifact conversion lock index')
 owner,digest=_identity(owner,0x6e7,payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  old=_previous(db,operation,digest);before=load_items(db,owner);ed=balances(db,owner)['ed']
  item=next((i for i in before if i['uid']==uid),None)
  if old is not None:
   current={(i['group'],i['slot']):i for i in before}
   return [acknowledgement(uid,ed,current_changes(db,operation,owner,0x6e7,old,before),options=item.get('option_groups',{}).get('31',[]) if item else [])]
  if item is None or item['group']!=1 or item['count']!=1 or item.get('identified') is False:raise ValueError('Owned identified unequipped Mirror Artifact required')
  require_current(item);require_unlocked(item)
  previous=item.get('option_groups',{});current=validate(item['template'],previous.get('31',[]))
  # 362D8F0's ordinary sender requires three existing conversion effects.
  if not all(current):raise ValueError('Native initial conversion effects are missing')
  needed=1+len(locked_options);priority=catalog()['conversion']['ticket_priority']
  tickets=sorted((i for i in before if i['group']==4 and i['template'] in priority and not expired(i) and not locked(i)),key=lambda i:(priority.index(i['template']),i.get('expires_at',2**63),i['slot']))
  if sum(i['count'] for i in tickets)<needed:raise ValueError('Artifact conversion tickets insufficient')
  updated={**previous,'31':draw(current,locked_options,randbelow)}
  positions=[(item['group'],item['slot'])]
  for ticket in tickets:
   count=min(needed,ticket['count']);positions.append(consume(db,owner,ticket,count)[0]);needed-=count
   if not needed:break
  replace(db,owner,uid,previous,updated)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  result=[acknowledgement(uid,ed,[(p,current.get(p)) for p in positions],options=updated['31'])]
  _commit(db,operation,digest,owner,0x6e7,positions,before,after)
  return result
