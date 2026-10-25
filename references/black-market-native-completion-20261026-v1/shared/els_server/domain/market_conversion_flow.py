"""Native six-coupon consumer before the unchanged paid17 handler."""
import struct
from els_server.domain.option_conversion_existing_flow import _session,_selected_authorizer
from els_server.protocol.market_conversion_messages import request,acknowledgement
def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x6e7 or not s.item_test or s.client_build!='dx11_260923':return None
 if not isinstance(event.payload,bytes)or len(event.payload)<6:return None
 mode=struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]
 if mode not in(17,18,19,22)or mode==17 and event.payload[-1]==0:return None
 uid=ed=0
 try:
  selection=_session(s);path,owner,account=selection
  if(type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Conversion current native request envelope')
  uid,_,_,_,_=request(event.payload);ed=s.account.get_reward_balances()['ed']
  from els_server.storage.market_conversion import perform
  return perform(path,owner,event.payload,s.shop_session_id+':market-conversion:'+str(owner)+':'+str(sequence),account_id=account,generation=s.shop_session_id,authorize=_selected_authorizer(s,selection))
 except(ValueError,OverflowError):return[acknowledgement(uid,ed,mode=mode,result=2005)]
