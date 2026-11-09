"""D56 armor role change at the original three NPC scenes."""
from els_server.protocol import neblon_role_change_messages as wire
from els_server.domain.neblon_role_change_rules import TOWNS

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0xd56 or s.client_build!='dx11_260923':return None
 try:
  wire.request(event.payload)
  from els_server.domain.option_conversion_existing_flow import _session,_selected_authorizer
  selection=_session(s);path,owner,account_id=selection;authorize=_selected_authorizer(s,selection)
  town=s.active_map
  if(type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))
     or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
     or town not in TOWNS or s.dungeon_return_pending or getattr(s,'town_warp_transition',None)is not None):raise ValueError('Role-change loaded actor/envelope')
  from els_server.domain.assembly_flow import _actor,_guard
  guard=_guard(s,_actor(s),town=True)
  def prepare(db,now):
   if not authorize()or s.active_map!=town or s.dungeon_return_pending or getattr(s,'town_warp_transition',None)is not None:raise ValueError('Obsolete role-change selection')
   guard(db,now);return True
  from els_server.storage.neblon_role_change import perform
  operation=s.shop_session_id+':neblon-role-change:'+str(owner)+':'+str(sequence)
  return perform(path,owner,event.payload,operation,account_id=account_id,prepare=prepare)
 except ValueError:return[wire.acknowledgement(result=2005)]
