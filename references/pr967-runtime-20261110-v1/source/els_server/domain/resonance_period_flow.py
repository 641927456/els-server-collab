"""Original718 selected-stat consumer; no generic219 emulation or client changes."""
import sqlite3
from els_server.protocol.resonance_period_messages import request,reply
from els_server.storage.resonance_period import use

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x718:return None
 from els_server.domain.town_travel_flow import _ordinary_actor
 if not _ordinary_actor(s):return[reply(result=256)]
 try:
  if event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Original718 envelope')
  request(event.payload)
  from els_server.domain.housing_access_flow import capture
  same,guard=capture(s)
  operation=s.shop_session_id+':resonance-period:'+str(s.account.uid)+':'+str(sequence)
  return use(s.account.store.path,s.account.uid,s.account.account_id,event.payload,operation,guard)
 except(ValueError,sqlite3.Error,OverflowError):return[reply(result=256)]if'same'not in locals()or same()else[]
