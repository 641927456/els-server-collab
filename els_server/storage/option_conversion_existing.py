"""One atomic paid reroll of a preexisting full weapon29. No producer or preview."""
import secrets,sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.option_conversion_existing import catalog,draw
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.option_conversion_existing_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.equipment_options import replace
from els_server.storage.npc_trade import balances,charge
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character

def _authority(db,owner,account_id,authorize):
 require_active_character(db,owner);require_owner(db,owner,account_id)
 if authorize is not None and not authorize():raise ValueError('Obsolete conversion session')

def perform(path,owner,payload,operation,randbelow=secrets.randbelow,encode=acknowledgement,*,account_id,authorize=None):
 uid=request(payload);owner,digest=_identity(owner,0x6e7,payload,operation)
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  _authority(db,owner,account_id,authorize)
  old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  item=next((i for i in before if i['uid']==uid),None)
  if old is not None:
   event=encode(uid if item is not None else 0,balance['ed'],current_changes(db,operation,owner,0x6e7,old,before));encode_event(event);_authority(db,owner,account_id,authorize);return [event]
  if item is None or item['group'] not in (1,9) or item['count']!=1 or item.get('identified')is False or item.get('sealed')or item.get('enhancement',0)<0:raise ValueError('Owned identified unsealed weapon required')
  require_current(item);require_unlocked(item);previous=item.get('option_groups',{})
  from els_server.domain.option_conversion_existing import validate
  values=validate(item['template'],previous.get('29',[]));fee=catalog()['compatibility']['fee_ed']
  if balance['ed']<fee or balance['revision']>=2**63-1:raise ValueError('Conversion ED or revision bound')
  updated=draw(item['template'],values,randbelow);_authority(db,owner,account_id,authorize);post_ed=charge(db,owner,balance,fee)
  replace(db,owner,uid,previous,{**previous,'29':updated})
  after=load_items(db,owner);current=next(i for i in after if i['uid']==uid);positions=[(current['group'],current['slot'])]
  event=encode(uid,post_ed,[(positions[0],current)]);encode_event(event)
  _authority(db,owner,account_id,authorize)
  _commit(db,operation,digest,owner,0x6e7,positions,before,after)
  _authority(db,owner,account_id,authorize)
  return [event]
