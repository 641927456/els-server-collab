"""Original1C0 envelope/selected lease; reuse shared atomic decomposition."""
from els_server.protocol.protocol_codec import Event
from els_server.protocol.inventory_management_messages import decompose_ack
from els_server.domain.equipment_engrave_flow import current_lease
def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x1c0 or not s.item_test or s.client_build!='dx11_260923':return None
 try:
  if not current_lease(s):raise ValueError('Obsolete decomposition lease')
  if(s.role!='game'or s.phase!='town_ready'or s.account.characters is None or s.account.store is None or s.account.store.uid!=s.account.uid
     or type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Decomposition session envelope')
  from els_server.storage.decomposition import decompose
  if not current_lease(s):raise ValueError('Obsolete decomposition lease')
  return decompose(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
 except ValueError:return [Event(0x201,kind=0x1c1,payload=decompose_ack(result=-1))]
