"""Original 9CF/9D0 wedge use; flag, material and receipt are atomic."""
import sqlite3,struct
from contextlib import closing
from els_server.domain.artifact_progression import catalog,slots
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.domain.fashion_state import record,empty_record
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items
from els_server.storage.artifact_progression import consume
from els_server.storage.artifact_equipment_state import replace
def request(payload):
 if not isinstance(payload,bytes) or len(payload)!=16:raise ValueError('Artifact slot expansion request size')
 material,target=struct.unpack('>QQ',payload)
 if not 0<material<2**63 or not 0<target<2**63 or material==target:raise ValueError('Artifact slot expansion instance IDs')
 return material,target
def acknowledgement(changes=(),result=0):
 rows=list(changes)
 return Event(0x201,kind=0x9d0,payload=struct.pack('>iI',result,len(rows))+b''.join(empty_record(*p) if i is None else record(i) for p,i in rows))
def perform(path,owner,payload,operation):
 material_uid,target_uid=request(payload);owner,digest=_identity(owner,0x9cf,payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  old=_previous(db,operation,digest);before=load_items(db,owner);by_uid={i['uid']:i for i in before}
  if old is not None:
   current={(i['group'],i['slot']):i for i in before}
   return [acknowledgement(current_changes(db,operation,owner,0x9cf,old,before))]
  material=by_uid.get(material_uid);item=by_uid.get(target_uid)
  if material is None or material['template'] not in catalog()['socket_expand_items']:raise ValueError('Owned original Artifact socket wedge required')
  if item is None or item['group']!=1 or not slots(item['template']) or item['count']!=1 or item.get('identified') is False:raise ValueError('Owned unequipped identified Artifact required')
  require_current(item);require_unlocked(item)
  if item.get('artifact_socket_open',False):raise ValueError('Artifact spirit-slot is already open')
  positions=[(item['group'],item['slot']),consume(db,owner,material)[0]]
  replace(db,owner,target_uid,False,True)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  result=[acknowledgement([(p,current.get(p)) for p in positions])]
  _commit(db,operation,digest,owner,0x9cf,positions,before,after)
  return result
