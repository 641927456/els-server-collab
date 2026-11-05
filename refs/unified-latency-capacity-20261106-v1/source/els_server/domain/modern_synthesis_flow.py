"""Exact native Magmelia/Alys menu authority for existing ordinary stones."""
from els_server.protocol.protocol_codec import Event
from els_server.protocol.modern_synthesis_messages import ack
from els_server.domain.equipment_engrave_flow import current_lease

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0xc68 or not s.item_test or s.client_build!='dx11_260923':return None
 try:
  if not current_lease(s):raise ValueError('Obsolete synthesis lease')
  if(s.role!='game'or s.phase!='town_ready'or s.account.characters is None or s.account.store is None or s.account.store.uid!=s.account.uid or
     type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Synthesis envelope')
  from els_server.domain.modern_synthesis_rules import catalog
  from els_server.storage.local_state import TOWN_SCENES
  npc=catalog()['npc']
  if(s.active_map!=npc['town']or s.pending_map!=npc['town']or s.account.get_location()['map']!=npc['town']or TOWN_SCENES.get(s.active_map)!=npc['world']or not {0x225,0x227}<=s.completed):raise ValueError('Current original synthesis NPC scene')
  from els_server.storage.modern_synthesis import perform
  if not current_lease(s):raise ValueError('Obsolete synthesis lease')
  return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
 except ValueError:return[Event(0x201,kind=0xc69,payload=ack(result=-1))]
