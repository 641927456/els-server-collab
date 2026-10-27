"""Restore a broken owned item atomically, retaining all other instance state."""
import sqlite3
from contextlib import closing
from els_server.domain.item_expiration import expired,require_current
from els_server.domain.item_locks import locked,require_unlocked
from els_server.protocol.equipment_restoration_messages import request,acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.profession_state import require_owner
from els_server.storage.item_instances import remove
from els_server.storage.equipment_enhancement import replace

def restore(path,owner,payload,operation,*,account_id=None):
 uid,template=request(payload);owner,digest=_identity(owner,0x21f,payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  if account_id is not None:require_owner(db,owner,account_id)
  old=_previous(db,operation,digest);before=load_items(db,owner)
  current={(i['group'],i['slot']):i for i in before}
  if old is not None:
   return [Event(0x201,kind=0x220,payload=acknowledgement(changes=current_changes(db,operation,owner,0x21f,old,before)))]
  item=next((i for i in before if i['uid']==uid),None)
  if item is None or item['count']!=1 or item['group'] not in (1,9) or not -13<=item.get('enhancement',0)<=-8:raise ValueError('Owned broken equipment required')
  require_current(item);require_unlocked(item)
  material=next((i for i in before if i['template']==template and i['group']==4 and not expired(i) and not locked(i)),None)
  if material is None:raise ValueError('Missing owned current restoration scroll')
  if material['count']==1:remove(db,owner,material)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,material['uid']))
  replace(db,owner,uid,item['enhancement'],-item['enhancement'])
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  positions=[(material['group'],material['slot']),(item['group'],item['slot'])]
  wire=acknowledgement(changes=[(p,current.get(p)) for p in positions])
  _commit(db,operation,digest,owner,0x21f,positions,before,after)
  return [Event(0x201,kind=0x220,payload=wire)]
