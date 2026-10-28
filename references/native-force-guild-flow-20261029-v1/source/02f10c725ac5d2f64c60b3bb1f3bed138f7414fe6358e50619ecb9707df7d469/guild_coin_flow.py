"""Original inventory524 donation,522 native guild currency read, stable town."""
import sqlite3
from els_server.protocol import guild_coin_messages as wire
def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in(0x524,0x522,0x50e,0x526,0x508,0x50a,0x50c)or s.client_build!='dx11_260923':return None
 try:
  from els_server.domain.guild_agit_flow import _capture as scene_capture
  from els_server.domain.housing_access_flow import capture
  same,guard=scene_capture(s) if getattr(s,'guild_agit',None)is not None else capture(s)
  if event.kind in(0x526,0x508,0x50a,0x50c) and s.phase!='guild_agit_ready':raise ValueError('Guild bank requires native505 ready scene')
  if event.performers not in((),(0,))or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Guild coin native envelope')
  from els_server.storage.guild_coin_state import read,perform
  if event.kind in(0x50a,0x50c):
   from els_server.storage.guild_bank_items import perform as transfer
   return transfer(s.account.store.path,s.account.uid,s.account.account_id,event.kind,event.payload,s.shop_session_id+':guild-transfer:'+str(s.account.uid)+':'+str(sequence),guard)
  if event.kind in(0x526,0x508):
   from els_server.storage import guild_bank_capacity as bank
   if event.kind==0x508:
    if event.payload:raise ValueError('Guild bank original empty read')
    return bank.read(s.account.store.path,s.account.uid,s.account.account_id,guard)
   return bank.perform(s.account.store.path,s.account.uid,s.account.account_id,event.payload,s.shop_session_id+':guild-capacity:'+str(s.account.uid)+':'+str(sequence),guard)
  if event.kind==0x50e:
   from els_server.storage.guild_bank_history import read as history
   return history(s.account.store.path,s.account.uid,s.account.account_id,event.payload,guard)
  if event.kind==0x522:
   if event.payload!=bytes(4):raise ValueError('Guild coin original read selector')
   return[wire.balance_reply(read(s.account.store.path,s.account.uid,s.account.account_id,guard))]
  return perform(s.account.store.path,s.account.uid,s.account.account_id,event.payload,s.shop_session_id+':guild-coin:'+str(s.account.uid)+':'+str(sequence),guard)
 except(ValueError,sqlite3.Error,OverflowError,AttributeError):
  if'same'not in locals()or not same():return[]
  if event.kind in(0x50a,0x50c):
   from els_server.protocol import guild_bank_transfer_messages as transfer
   return[transfer.deposited(result=0xb28)]if event.kind==0x50a else[transfer.withdrawn(result=0xb28)]
  if event.kind in(0x526,0x508):
   from els_server.protocol import guild_bank_capacity_messages as bank
   return[bank.overview(16,result=0xb43)]if event.kind==0x508 else[bank.expanded(0,0,0,result=0xb28)]
  if event.kind==0x50e:
   from els_server.protocol.guild_bank_history_messages import reply
   return[reply(1,1,2,result=0xb28)]
  return[wire.balance_reply(0,result=0xb28)]if event.kind==0x522 else[wire.donated(0,0,0,result=0xb28)]
