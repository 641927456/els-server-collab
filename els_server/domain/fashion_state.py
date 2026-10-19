"""Native 104/105 costume moves; all affected slots commit in one SQL transaction.

The native request contains bag/slot pairs, no operation nonce or item UID. TCP
frame replay protection belongs to the transport. A fresh same-slot swap is a
new operation, so payload-only caching would incorrectly suppress real swaps.
"""
import json,sqlite3,struct
from contextlib import closing
from els_server.storage.character_schema import character_uid
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS,LOCAL_BAG_CAPACITY,validate_item,item_body,fixture
from els_server.domain.bag_capacity import wire_limit
from els_server.storage.inventory_state import load_items

def move_request(payload):
 if not isinstance(payload,bytes) or len(payload)!=11:raise ValueError('Fashion move request length')
 sg,ss,dg,ds,flag=struct.unpack('>BiBiB',payload)
 if flag!=0 or sg not in (7,27,9) or dg not in (7,27,9) or (sg,ss)==(dg,ds):raise ValueError('Unsupported fashion move')
 for group,slot in ((sg,ss),(dg,ds)):
  if group in (7,27) and not 0<=slot<wire_limit(group) or group==9 and slot not in FASHION_EQUIP_SLOTS.values():raise ValueError('Fashion move slot bound')
 return (sg,ss),(dg,ds)

def empty_record(group,slot):
 # Original private 234B280 decoded UID/template/count 0 with this 304-byte body.
 body=bytearray(item_body(dict(uid=1,template=81021,metadata=0,count=1,group=27,slot=0)))
 for f in fixture()['fields']:
  if int(f['offset'],0) in (0,5):struct.pack_into('>i',body,f['wire_offset'],0)
 return struct.pack('>QBh',0,group,slot)+body+bytes(9)

def record(item):
 i=validate_item(item)
 return struct.pack('>QBh',i['uid'],i['group'],i['slot'])+item_body(i)+bytes(9)

def move_ack(changes=(),result=0):
 # 234B280: DD46E0 vector first, then signed int result.
 return struct.pack('>I',len(changes))+b''.join(empty_record(*pos) if item is None else record(item) for pos,item in changes)+struct.pack('>i',result)

def equipment_map(items):
 # D9B170 +12E -> DB0AC0/DD0470: int equipment slot -> DB4F80 item wrapper.
 equipped=sorted((validate_item(i) for i in items if i['group']==9),key=lambda i:i['slot'])
 return struct.pack('>I',len(equipped))+b''.join(struct.pack('>i',i['slot'])+record(i) for i in equipped)

def move_fashion(path,payload,uid=1001):
 uid=character_uid(uid)
 source,destination=move_request(payload)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON')
  db.execute('BEGIN IMMEDIATE')
  from els_server.storage.bag_capacity import allowances
  limits=allowances(db,uid)
  if any(g!=9 and s>=limits[g] for g,s in (source,destination)):raise ValueError('Unowned fashion bag position')
  items=load_items(db,uid);by_pos={(i['group'],i['slot']):i for i in items}
  first=by_pos.get(source);second=by_pos.get(destination)
  if first is None:raise ValueError('Fashion source slot is empty')
  from els_server.domain.item_expiration import require_current
  for item in (first,second):
   if item:require_current(item)
  if first['template'] not in FASHION_EQUIP_SLOTS or second is not None and second['template'] not in FASHION_EQUIP_SLOTS:raise ValueError('Non-fashion move')
  moved=validate_item({**first,'group':destination[0],'slot':destination[1]})
  swapped=validate_item({**second,'group':source[0],'slot':source[1]}) if second else None
  if any(i and i['group']==9 for i in (moved,swapped)):
   from els_server.game_data import client_data
   identities=db.execute("SELECT 1 FROM sqlite_master WHERE name='characters' AND type='table'").fetchone()
   row=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(uid,)).fetchone() if identities else (1,1) if uid==1001 else None
   if row is None:raise ValueError('Unknown fashion owner')
   from els_server.domain.equipment_requirements import class_matches
   for i in (moved,swapped):
    if not i or i['group']!=9:continue
    raw=client_data().item(i['template'])['record']
    if raw[210] and raw[210]!=row[0] or not class_matches(row[1],raw[211]):raise ValueError('Fashion character requirement')
    if raw[8]&4 and row[0]!=10:raise ValueError('Companion fashion character requirement')
  changes=[(source,swapped),(destination,moved)]
  response=move_ack(changes)
  db.execute('CREATE TABLE IF NOT EXISTS fashion_moves (id INTEGER PRIMARY KEY, request BLOB NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL)')
  # Retained UIDs move through transaction-local negative slots. Deleting a
  # retained row fires instance-child cascades and deletion observers.
  for old in (first,second):
   if old and db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',(-old['uid'],old['uid'],uid)).rowcount!=1:raise ValueError('Fashion move source owner mismatch')
  for i in (moved,swapped):
   if i and db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=? AND owner=?',(i['group'],i['slot'],i['uid'],uid)).rowcount!=1:raise ValueError('Fashion move retained owner mismatch')
  after=load_items(db,uid)
  expected={i['uid']:i for i in items};expected.update({i['uid']:i for i in (moved,swapped) if i})
  if expected!={i['uid']:i for i in after}:raise ValueError('Fashion move changed inventory instance state')
  db.execute('INSERT INTO fashion_moves(request,before_json,after_json) VALUES (?,?,?)',(payload,json.dumps([first,second],sort_keys=True),json.dumps([swapped,moved],sort_keys=True)))
  return response
