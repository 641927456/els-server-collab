"""Atomic opening of the owned 723621 abyss accessory box.

The generic fixed-cube branch grants only row['entries'][0], so this explicit
transaction delivers all three accessories and replays from the ledger.
"""
import sqlite3,struct
from contextlib import closing
from els_server.domain.boosting_2026_abyss_accessory import BOX,definition
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event


def open_box(path,owner,payload,operation):
 request=use_request(payload)
 if request.option or request.choices or any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3)):raise ValueError('Abyss accessory box is all-output, no choices')
 outputs=definition()['entries']
 owner,digest=_identity(owner,0x196,struct.pack('>i',BOX)+payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  if old is not None:return _updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
  source=next((i for i in before if i['uid']==request.uid),None)
  if source is None or source['template']!=BOX or source['group']!=4:raise ValueError('Owned abyss accessory box required')
  require_current(source);require_unlocked(source)
  if balance['revision']>=2**63-1:raise ValueError('Abyss accessory revision overflow')
  position=(source['group'],source['slot'])
  if source['count']==1:remove(db,owner,source)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(source['uid'],owner))
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
  plans=[dict(template=r['template'],metadata=VERIFIED_TEMPLATES[r['template']],group=TEMPLATE_BAG_GROUPS[r['template']],quantity=r['quantity']) for r in outputs]
  grants=grant_items(db,plans,owner,selected_accessory_box=BOX);after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=sorted({position,*[(i['group'],i['slot']) for i in grants]});events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(r['template'],r['quantity']) for r in outputs])
  for event in events:encode_event(event)
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));_commit(db,operation,digest,owner,0x196,positions,before,after);return events
