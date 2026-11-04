"""Six finite native coupons; debit, preview/apply and response commit together."""
from contextlib import closing
from pathlib import Path
from uuid import UUID
import json,secrets,sqlite3,time
from els_server.domain import market_conversion_rules as rules
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.market_conversion_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import market_conversion_pending as pending
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.equipment_options import replace
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character

def _authority(db,path,owner,account,authorize):
 main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
 if not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=path or any(r[1]not in('main','temp')for r in db.execute('PRAGMA database_list'))or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Conversion exact original writer')
 require_active_character(db,owner);require_owner(db,owner,account)
 if not callable(authorize)or authorize()is not True:raise ValueError('Obsolete conversion actor or lease')
def _usable(item,now):
 if item.get('sealed')or item['count']<1:raise ValueError('Conversion eligible coupon')
 require_current(item,now=now);require_unlocked(item,now=now)
def _take(db,owner,before,templates,now):
 eligible=[]
 for item in before:
  if item['template']not in templates or item['group']!=4:continue
  try:_usable(item,now)
  except ValueError:continue
  eligible.append(item)
 if not eligible:raise ValueError('Current matching conversion coupon required')
 source=min(eligible,key=lambda i:(i.get('expires_at',float('inf')),i['slot'],i['uid']))
 if source['count']==1:remove(db,owner,source)
 elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',(source['uid'],owner,source['count'])).rowcount!=1:raise ValueError('Conversion coupon writer changed')
 return source['group'],source['slot']
def _equipment(item,now):
 if item is None or item['group']!=1 or item['count']!=1 or item.get('identified')is False or item.get('sealed')or item.get('enhancement',0)<0:raise ValueError('Owned identified unsealed unequipped conversion target required')
 require_current(item,now=now);require_unlocked(item,now=now)
 return rules.target(item['template'])
def _preview(db,owner,account,generation,item,operation=None):
 p=pending.get(db,owner)
 if p is None or p['account_id']!=account or p['item_uid']!=item['uid']or p['generation']!=generation or p['basis_json']!=pending.basis(item)or operation is not None and p['operation']!=operation:raise ValueError('Original current paid conversion preview required')
 return rules.validate(item['template'],json.loads(p['options_json']))
def perform(path,owner,payload,operation,randbelow=secrets.randbelow,encode=acknowledgement,*,account_id,generation,authorize):
 uid,mode,tail,slot,value=request(payload);owner,digest=_identity(owner,0x6e7,payload,operation)
 if type(generation)is not str or str(UUID(generation))!=generation or UUID(generation).version!=4 or not operation.startswith(generation+':market-conversion:'+str(owner)+':'):raise ValueError('Conversion original generation/operation')
 path=Path(path).resolve()
 with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=int(time.time())
  _authority(db,path,owner,account_id,authorize)
  old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  item=next((i for i in before if i['uid']==uid),None)
  if old is not None:
   options=_preview(db,owner,account_id,generation,item,operation)if mode==18 and item is not None else[]
   if mode==18 and item is None:raise ValueError('Conversion preview target no longer present')
   event=encode(uid if item is not None else 0,balance['ed'],current_changes(db,operation,owner,0x6e7,old,before),mode=mode,options=options)
   encode_event(event);_authority(db,path,owner,account_id,authorize);return[event]
  target=_equipment(item,now);index=target['index'];previous=item.get('option_groups',{});values=previous.get('29')
  if values is None:
   if mode!=17 or index!=1:raise ValueError('Complete existing native conversion effects required')
  else:values=rules.validate(item['template'],values)
  positions=[(item['group'],item['slot'])];options=[];post_ed=balance['ed']
  if mode==19:
   options=_preview(db,owner,account_id,generation,item)
   replace(db,owner,uid,previous,{**previous,'29':options});pending.clear(db,owner);options=[]
  elif mode==22:
   updated=rules.upgrade(item['template'],values,slot,value)
   positions.append(_take(db,owner,before,(136239,)if index==0 else(119343,),now))
   replace(db,owner,uid,previous,{**previous,'29':updated});pending.clear(db,owner)
  elif mode in(17,18):
   if index==0:
    # Existing paid17 is handled by its unchanged original consumer.
    if mode!=18 or tail:raise ValueError('Market weapon consumer is native paid18 only')
    positions.append(_take(db,owner,before,(136199,136201),now))
    fee=rules.catalog()['rules']['0']['fee']
    if balance['ed']<fee:raise ValueError('Conversion original ED insufficient')
    post_ed=charge(db,owner,balance,fee)
   else:
    if not tail:raise ValueError('Market armor uses original material checkbox')
    positions.append(_take(db,owner,before,(119325,),now))
    if mode==18:positions.append(_take(db,owner,before,(119329,119328),now))
   updated=rules.draw(item['template'],randbelow)
   if mode==18:
    pending.put(db,owner,account_id,uid,generation,operation,item,updated);options=updated
   else:
    replace(db,owner,uid,previous,{**previous,'29':updated});pending.clear(db,owner)
  else:raise ValueError('Unsupported market native consumer')
  _authority(db,path,owner,account_id,authorize)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=list(dict.fromkeys(positions))
  event=encode(uid,post_ed,[(p,current.get(p))for p in positions],mode=mode,options=options);encode_event(event)
  _authority(db,path,owner,account_id,authorize)
  _commit(db,operation,digest,owner,0x6e7,positions,before,after)
  _authority(db,path,owner,account_id,authorize);return[event]
