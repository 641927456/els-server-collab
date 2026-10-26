"""F ranking requests get a native failure while score sources remain unqualified."""
from els_server.protocol.board_ranking_messages import request,unavailable
from els_server.protocol.protocol_codec import encode_event
ENABLED=True

def handle(session,event,sequence):
 if(event.event_id!=0x202 or event.kind!=0x202
    or session.client_build!='dx11_260923' or getattr(session,'active_map',None)!=1012):return None
 if not ENABLED:return []
 try:
  from els_server.domain.equipment_chip_flow import reset_context
  reset_context(session,event,sequence)
 except(ValueError,AttributeError):return []
 try:category,_page=request(event.payload)
 except ValueError:category=-1
 answer=unavailable(category);encode_event(answer)
 return [answer]
