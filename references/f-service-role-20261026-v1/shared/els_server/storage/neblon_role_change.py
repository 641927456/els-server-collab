"""Existing armor/coupon and full native D57 in one original SQL transaction."""
from pathlib import Path
from contextlib import closing
from uuid import UUID
import json,sqlite3,struct,time
from els_server.domain.neblon_role_change_rules import family
from els_server.domain.inventory_items import validate_item
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.neblon_role_change_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.item_instances import remove
WRITER_ENABLED=True

def _authority(db,path,owner,account_id,prepare,now):
 main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
 if(not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=path
    or any(r[1]not in('main','temp')for r in db.execute('PRAGMA database_list'))
    or db.execute('PRAGMA foreign_keys').fetchone()!=(1,)or not callable(prepare)):raise ValueError('Neblon original writer/path')
 require_active_character(db,owner);require_owner(db,owner,account_id)
 if prepare(db,now)is not True:raise ValueError('Obsolete Neblon selected actor')

def _target(item,now):
 if item is None or(item['group'],item['metadata'],item['count'])!=(1,1,1)or item.get('identified')is False or item.get('sealed'):
  raise ValueError('Neblon current owned identified unsealed bag armor')
 validate_item(item);require_current(item,now=now);require_unlocked(item,now=now)

def _history(db,operation,digest,owner,template):
 r=db.execute('SELECT owner,kind,request_hash,positions_json,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
 if r is None or r[:3]!=(owner,0xd56,digest):raise ValueError('Neblon exact original receipt')
 try:
  positions=json.loads(r[3]);before=json.loads(r[4]);after=json.loads(r[5])
  if type(before)is not list or len(before)!=2 or type(after)is not list or len(after)not in(1,2):raise ValueError('Neblon receipt shape')
  first,coupon=before;last=after[0];f=family(first['template'],template)
  for item in before+after:validate_item(item)
  if positions!=[[i['group'],i['slot']]for i in before]or coupon['template']not in f['coupons']or coupon['group']!=4:raise ValueError('Neblon receipt original positions/material')
  if last!=dict(first,template=template):raise ValueError('Neblon receipt altered armor attributes')
  expected=[]if coupon['count']==1 else[dict(coupon,count=coupon['count']-1)]
  if after[1:]!=expected:raise ValueError('Neblon receipt material count')
  return first['uid']
 except(KeyError,TypeError,json.JSONDecodeError)as e:raise ValueError('Malformed Neblon role-change receipt')from e

def perform(path,owner,payload,operation,*,account_id,prepare,encode=acknowledgement):
 if not WRITER_ENABLED:raise ValueError('New Neblon character changes closed')
 uid,template=request(payload)
 if type(account_id)is not int or not 1<=account_id<2**63 or type(operation)is not str:raise ValueError('Neblon operation account')
 generation=operation.split(':',1)[0]
 if(str(UUID(generation))!=generation or UUID(generation).version!=4
    or not operation.startswith(generation+':neblon-role-change:'+str(owner)+':')):raise ValueError('Neblon original operation generation')
 owner,digest=_identity(owner,0xd56,struct.pack('>Q',account_id)+payload,operation);path=Path(path).resolve()
 with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=int(time.time());_authority(db,path,owner,account_id,prepare,now)
  old=_previous(db,operation,digest);before=load_items(db,owner);owned={i['uid']:i for i in before};item=owned.get(uid)
  if old is not None:
   if _history(db,operation,digest,owner,template)!=uid:raise ValueError('Neblon receipt requested UID')
   if item is None or item['template']!=template or item['group']!=1:event=encode(result=2005)
   else:
    from els_server.storage.equipment_receipt_state import current_changes
    event=encode(template,current_changes(db,operation,owner,0xd56,old,before))
   encode_event(event);_authority(db,path,owner,account_id,prepare,now);return[event]
  _target(item,now);rule=family(item['template'],template)
  candidates=[]
  for material in before:
   if material['template']not in rule['coupons']or material['group']!=4 or material.get('sealed'):continue
   try:require_current(material,now=now);require_unlocked(material,now=now)
   except ValueError:continue
   candidates.append(material)
  if not candidates:raise ValueError('Matching usable Neblon role coupon required')
  coupon=min(candidates,key=lambda i:(i.get('expires_at',2**63-1),rule['coupons'].index(i['template']),i['slot'],i['uid']))
  for table in('inventory_items','inventory_action_receipts','spell_socket_pending','market_conversion_pending'):
   if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND lower(tbl_name)=?",(table,)).fetchone():raise ValueError('Unreviewed Neblon writer trigger')
  wallet=db.execute('SELECT * FROM reward_balances WHERE uid=?',(owner,)).fetchall()
  if not wallet:raise ValueError('Neblon original wallet missing')
  if coupon['count']==1:remove(db,owner,coupon)
  elif db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=? AND count=?',(owner,coupon['uid'],coupon['count'])).rowcount!=1:raise ValueError('Neblon stale coupon count')
  if db.execute('UPDATE inventory_items SET template=? WHERE owner=? AND uid=? AND template=?',(template,owner,uid,item['template'])).rowcount!=1:raise ValueError('Neblon original armor instance changed')
  from els_server.storage import spell_socket_pending,market_conversion_pending
  spell_socket_pending.cancel(db,owner,[uid])
  pending=market_conversion_pending.get(db,owner)
  if pending is not None and pending['item_uid']==uid:market_conversion_pending.clear(db,owner)
  after=load_items(db,owner);current={i['uid']:i for i in after};expected={k:dict(v)for k,v in owned.items()};expected[uid]=dict(item,template=template)
  if coupon['count']==1:expected.pop(coupon['uid'])
  else:expected[coupon['uid']]=dict(coupon,count=coupon['count']-1)
  if current!=expected or db.execute('SELECT * FROM reward_balances WHERE uid=?',(owner,)).fetchall()!=wallet:raise ValueError('Neblon changed unrelated inventory or wallet')
  positions=[(item['group'],item['slot']),(coupon['group'],coupon['slot'])];event=encode(template,[(p,next((i for i in after if(i['group'],i['slot'])==p),None))for p in positions]);encode_event(event)
  _authority(db,path,owner,account_id,prepare,now)
  _commit(db,operation,digest,owner,0xd56,positions,[item,coupon],[current[uid]]+([current[coupon['uid']]]if coupon['uid']in current else[]))
  _authority(db,path,owner,account_id,prepare,now);return[event]
