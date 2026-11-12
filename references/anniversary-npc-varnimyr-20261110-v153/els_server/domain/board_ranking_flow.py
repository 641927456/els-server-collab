"""Board ranking requests get a native failure while score sources remain unqualified."""
from els_server.protocol.board_ranking_messages import request,unavailable
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.local_state import TOWN_SCENES
ENABLED=True

def handle(session,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x202 or session.client_build!='dx11_260923':return None
 from els_server.domain.trade_board_authority import BOARD_SCENES
 town=session.active_map
 if TOWN_SCENES.get(town) not in BOARD_SCENES:return None
 if not ENABLED:return []
 try:
  from els_server.domain.equipment_chip_flow import reset_context
  reset_context(session,event,sequence)
 except(ValueError,AttributeError):return []
 if (session.pending_map!=town or session.dungeon_return_pending
     or getattr(session,'town_warp_transition',None) is not None):return []
 try:category,_page=request(event.payload)
 except ValueError:category=-1
 answer=unavailable(category);encode_event(answer)
 return [answer]
