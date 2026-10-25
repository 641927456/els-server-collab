"""Existing admitted fixed-level scrolls through original221/222, atomically."""
import sqlite3,struct
from contextlib import closing
from els_server.game_data import client_data
from els_server.domain.normal_equipment import definitions
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_restoration_messages import acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.profession_state import require_owner
from els_server.storage.item_instances import remove
from els_server.storage.equipment_enhancement import replace

SCROLLS=frozenset((130149,130150,130151,130152))

def apply(path,owner,payload,operation,*,account_id=None,prepare=None):
 if not isinstance(payload,bytes)or len(payload)!=16:raise ValueError('Enhancement scroll request size')
 uid,material_uid=struct.unpack('>QQ',payload)
 if not 0<uid<2**63 or not 0<material_uid<2**63 or uid==material_uid:raise ValueError('Enhancement scroll identities')
 owner,digest=_identity(owner,0x221,payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  if prepare is not None:prepare()
  from els_server.storage.item_actor import require_active_character
  require_active_character(db,owner)
  if account_id is not None:require_owner(db,owner,account_id)
  old=_previous(db,operation,digest);before=load_items(db,owner)
  if old is not None:
   wire=acknowledgement(changes=current_changes(db,operation,owner,0x221,old,before))
   return [Event(0x201,kind=0x222,payload=wire)]
  by_uid={i['uid']:i for i in before};target=by_uid.get(uid);material=by_uid.get(material_uid)
  if target is None or target['count']!=1 or target['group']!=1 or target['template']not in definitions():raise ValueError('Owned unequipped normal equipment required')
  if material is None or material['template']not in SCROLLS or material['group']!=4:raise ValueError('Owned admitted enhancement scroll required')
  require_current(target);require_current(material);require_unlocked(target);require_unlocked(material)
  d=client_data().item(target['template'])
  from els_server.domain.boosting_2026_participation_gear import cannot_enhance
  if cannot_enhance(target['template'])or d['flags4']&0xa1 or d['item_type']not in(1,2):raise ValueError('Equipment cannot receive enhancement scroll')
  rule=client_data().enchanting.scroll(material['template'])['definition']
  if set(rule)-{'ID','ENCHANT_LEVEL'}:raise ValueError('Unreviewed scroll restriction')
  level=rule['ENCHANT_LEVEL'];previous=target.get('enhancement',0)
  if type(level)is not int or not 1<=level<=13 or not 0<=previous<level:raise ValueError('Scroll must increase an unbroken target')
  if material['count']==1:remove(db,owner,material)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,material_uid))
  replace(db,owner,uid,previous,level)
  from els_server.domain.enhancement_progress import after as progress_after
  from els_server.storage.enhancement_progress import replace as replace_progress
  gauge,points=progress_after(target,0,0,level)
  replace_progress(db,owner,dict(target,enhancement=level),gauge,points)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  positions=[(target['group'],target['slot']),(material['group'],material['slot'])]
  wire=acknowledgement(changes=[(p,current.get(p))for p in positions])
  event=Event(0x201,kind=0x222,payload=wire)
  from els_server.protocol.protocol_codec import encode_event
  encode_event(event) # Complete event encoding precedes receipt and SQL commit.
  if prepare is not None:prepare()
  _commit(db,operation,digest,owner,0x221,positions,before,after)
  return [event]
