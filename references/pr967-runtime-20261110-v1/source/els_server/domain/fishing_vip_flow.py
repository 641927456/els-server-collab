"""Original219 coupons, stable selected actor, shared original19C service map."""
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.protocol.career_messages import use_request,use_ack
from els_server.storage import fishing_vip as storage

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x219:return None
 from els_server.domain.town_travel_flow import _ordinary_actor
 if not _ordinary_actor(s):return None
 try:source=use_request(event.payload)
 except ValueError:return None
 operation=s.shop_session_id+':fishing-vip:'+str(s.account.uid)+':'+str(sequence)
 with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
  row=db.execute('SELECT template FROM inventory_items WHERE owner=?AND uid=?',(s.account.uid,source)).fetchone()
  replay=db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()if db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone()else None
 if(row is None or row[0]not in storage.DAYS)and not replay:return None
 try:
  from els_server.domain.housing_access_flow import capture
  same,guard=capture(s)
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('FishingVIP original request envelope')
  return storage.use(s.account.store.path,s.account.uid,s.account.account_id,event.payload,operation,guard)
 except(ValueError,sqlite3.Error,OverflowError):return[use_ack(result=-1)]if'same'in locals()and same()else[]
