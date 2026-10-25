"""Reset scroll -> unidentified item -> paid-once scroll and free identification."""
import sqlite3,secrets
from contextlib import closing
from els_server.storage.profession_state import require_owner
from els_server.domain.identification_ui import require_template,catalog,draw_for_template
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.identification_messages import request,acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
from els_server.storage.equipment_options import replace as replace_options
from els_server.storage.equipment_identification import replace as replace_identified
def perform(path,owner,kind,payload,operation,randbelow=secrets.randbelow,*,account_id=None,prepare=None):
 uid,material_uid=request(kind,payload);owner,digest=_identity(owner,kind,payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  if prepare is not None:prepare()
  from els_server.storage.item_actor import require_active_character
  require_active_character(db,owner)
  if account_id is not None:require_owner(db,owner,account_id)
  old=_previous(db,operation,digest);before=load_items(db,owner);ed=balances(db,owner)['ed'];by_uid={i['uid']:i for i in before}
  if old is not None:
   current={(i['group'],i['slot']):i for i in before}
   return [Event(0x201,kind=kind+1,payload=acknowledgement(kind,ed,current_changes(db,operation,owner,kind,old,before)))]
  item=by_uid.get(uid)
  from els_server.domain.accessory_identification import supported as accessory_supported,draw as accessory_draw
  accessory=item is not None and accessory_supported(item['template'])
  if accessory and(kind!=0x438 or item['group']!=2):raise ValueError('Accessory initial identification requires original bag item')
  if item is None or item['count']!=1 or(item['group']!=1 and not accessory):raise ValueError('Owned unequipped identification item required')
  require_template(item['template']);require_current(item);require_unlocked(item)
  from els_server.domain.accessory_identification import initial_pending
  identified=item.get('identified',not initial_pending(item));previous=item.get('option_groups',{});positions=[(item['group'],item['slot'])]
  if kind==0x43a:
   if not identified:raise ValueError('Item is already unidentified')
   from els_server.domain.artifact_identification import supported,reset_values
   reset_options=reset_values(item['template'],previous.get('1',[])) if supported(item['template']) else []
   material=by_uid.get(material_uid)
   if material is None or str(material['template']) not in catalog()['materials']:raise ValueError('Owned original reset scroll required')
   require_current(material);require_unlocked(material)
   if material['count']==1:remove(db,owner,material)
   else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(material_uid,owner))
   positions.append((material['group'],material['slot']));updated={**previous,'1':reset_options};flag=False
  else:
   if identified:raise ValueError('Identify requires an unidentified item, not a free reroll')
   from els_server.domain.artifact_identification import supported,identify_values
   updated={**previous,'1':accessory_draw(randbelow) if accessory else identify_values(item['template'],previous.get('1',[]),randbelow) if supported(item['template']) else [draw_for_template(item['template'],randbelow(10000))]};flag=True
  if kind==0x438 and item['template'] in (168915,168916,168917,168918) and not previous.get('31'):
   from els_server.domain.artifact_conversion import draw as conversion_draw
   updated['31']=conversion_draw([0,0,0],{},randbelow)
  replace_identified(db,owner,uid,identified,flag);replace_options(db,owner,uid,previous,updated)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  wire=acknowledgement(kind,ed,[(p,current.get(p)) for p in positions])
  event=Event(0x201,kind=kind+1,payload=wire)
  from els_server.protocol.protocol_codec import encode_event
  encode_event(event)
  if prepare is not None:prepare()
  _commit(db,operation,digest,owner,kind,positions,before,after)
  return [event]
