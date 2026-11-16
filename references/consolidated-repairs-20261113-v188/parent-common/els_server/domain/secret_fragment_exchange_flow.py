"""Native tree223 routes through the existing atomic material-exchange writer."""
import sqlite3,struct
from contextlib import closing
from els_server.protocol.protocol_codec import Event
from els_server.protocol.fish_exchange_messages import acknowledgement
from els_server.domain import secret_fragment_exchange as rules

def handle(s,event,sequence):
 if(event.event_id!=0x202 or event.kind!=0x223 or len(event.payload)<4 or struct.unpack_from('>i',event.payload)[0]not in(40145,40146)):return None
 try:
  from els_server.domain.housing_access_flow import capture
  same,guard=capture(s)
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Native tree actor/envelope')
  r=rules.request(event.payload,s.active_map)
  from els_server.storage.material_exchange import exchange
  def ack(ed,changes=(),rewards=(),*,ed_reward=0):
   return acknowledgement(ed,changes,rewards,exchange_type=4,ed_reward=ed_reward)
  return exchange(s.account.store.path,s.account.uid,s.active_map,event.payload,s.shop_session_id+':tree-exchange:'+str(s.account.uid)+':'+str(sequence),r,
   account_id=s.account.account_id,source_quantity=rules.catalog()['source_quantity'],draw=rules.draw,acknowledgement=ack,guard=guard)
 except(ValueError,sqlite3.Error,OverflowError,AttributeError):
  if 'same'not in locals()or not same():return []
  with closing(sqlite3.connect(s.account.store.path))as db:
   row=db.execute('SELECT b.ed FROM reward_balances b JOIN character_owners o ON o.uid=b.uid WHERE b.uid=?AND o.account_id=?',(s.account.uid,s.account.account_id)).fetchone()
  return []if row is None else[Event(0x201,kind=0x224,payload=acknowledgement(row[0],result=-1,exchange_type=4))]
