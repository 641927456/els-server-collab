"""Captured original F actor and generation; a query snapshot is never authority."""
from els_server.domain.option_conversion_existing_flow import _session,_selected_authorizer
from els_server.domain.assembly_flow import _actor,_guard

class TradeBoardAuthority:
 __slots__=('session','path','owner','account_id','kind','_selected','_town_guard')
 def __init__(self,session,event,sequence):
  if(event.event_id!=0x202 or event.kind not in(0x9fc,0x9fe,0xa00,0xa02,0xa04,0xa06,0xa08,0xa0a,0xa0c,0xa11,0xa13,0xa18)or session.client_build!='dx11_260923'
     or type(sequence)is not int or not 0<sequence<2**32
     or event.performers not in((),(0,))or event.uid!=2**64-1
     or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('TradeBoard original purchase envelope')
  selection=_session(session);self.session=session;self.kind=event.kind;self.path,self.owner,self.account_id=selection
  self._selected=_selected_authorizer(session,selection);self._town_guard=_guard(session,_actor(session),town=True)
 def check(self,db,now):
  s=self.session
  if(not self._selected()or s.active_map!=1012 or s.dungeon_return_pending
     or getattr(s,'town_warp_transition',None)is not None):raise ValueError('TradeBoard obsolete original F actor')
  self._town_guard(db,now)
