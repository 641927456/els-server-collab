"""Compose actual D52 removal with original D50, shared-bank or seal writer.

No nested database, new schema, client packet fabrication or item production.
Every removal has both original D52 receipts inside the outer transaction.
"""
import struct,json
from els_server.domain.cartridge_registration_rules import scalar,owner_account,read_account
from els_server.protocol.equipment_cartridge_messages import request,acknowledge
from els_server.storage.inventory_actions import _identity,_previous
from els_server.storage.inventory_state import load_items

WRITER_ENABLED=True

def _writer(db):
 if not WRITER_ENABLED:raise ValueError('Cartridge composed transition writer closed')
 if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Cartridge original foreignkey write transaction required')
 tables=('account_cartridge_state','account_cartridge_collection','account_cartridge_binding_receipts','inventory_action_receipts')
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND lower(tbl_name) IN ("+','.join('?'for _ in tables)+') LIMIT 1',tables).fetchone():raise ValueError('Unknown Cartridge composed transition trigger')

def detach_for_transition(db,owner,item,operation,reason,*,authorize=None):
 if reason not in ('replacement','shared-bank','seal'):raise ValueError('Unqualified Cartridge composed transition')
 if scalar(item.get('cartridge',[0,0]))==[0,0]:return item
 _writer(db)
 from els_server.storage.account_cartridge_registration import _perform_binding_db
 # Only a current real owned inventory UID can be removed; never accept bank
 # JSON, an arbitrary scalar, a foreign character or stale caller snapshot.
 account_id=owner_account(db,owner);current=next((i for i in load_items(db,owner)if i['uid']==item['uid']),None)
 if current!=item:raise ValueError('Cartridge composed current owned item mismatch')
 suboperation=operation+':cartridge-composed-D52:'+reason+':'+str(item['uid'])
 _perform_binding_db(db,owner,account_id,0xd52,struct.pack('>Q',item['uid']),suboperation,authorize=authorize)
 after=next((i for i in load_items(db,owner)if i['uid']==item['uid']),None)
 if after is None or scalar(after.get('cartridge',[0,0]))!=[0,0]or {k:v for k,v in after.items()if k!='cartridge'}!={k:v for k,v in item.items()if k!='cartridge'}:raise ValueError('Cartridge composed D52 must preserve complete item')
 return after

def binding_in_original_transaction(db,owner,account_id,kind,payload,operation,*,authorize=None,encode=acknowledge):
 from els_server.storage.account_cartridge_registration import _perform_binding_db,_authority
 if kind!=0xd50:return _perform_binding_db(db,owner,account_id,kind,payload,operation,authorize=authorize,encode=encode)
 target_uid,selected=request(kind,payload);owner,digest=_identity(owner,kind,payload,operation)
 _authority(db,owner,account_id,authorize)
 # An old success is always interpreted by its unchanged original reader.
 try:previous=_previous(db,operation,digest)
 except(TypeError,KeyError,json.JSONDecodeError)as exc:raise ValueError('Malformed Cartridge binding previous')from exc
 if previous is not None:return _perform_binding_db(db,owner,account_id,kind,payload,operation,authorize=authorize,encode=encode)
 item=next((i for i in load_items(db,owner)if i['uid']==target_uid),None)
 if item is not None and scalar(item.get('cartridge',[0,0]))!=[0,0]:
  rows=read_account(db,account_id)['rows']
  # Replacing this carrier is supported. Moving a cartridge currently attached
  # to another UID/character remains subject to explicit manual D52 removal.
  if selected not in rows or rows[selected][0]!=0:raise ValueError('Replacement requires selected registered unbound Cartridge')
  detach_for_transition(db,owner,item,operation,'replacement',authorize=authorize)
 return _perform_binding_db(db,owner,account_id,kind,payload,operation,authorize=authorize,encode=encode)
