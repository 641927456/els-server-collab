"""Dedicated authenticated 8D1 color operation16, retaining other shared modes."""
import struct
from els_server.protocol.exascale_color_messages import request,acknowledgement
from els_server.domain.equipment_engrave_flow import current_lease

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x8d1 or not s.item_test or s.client_build!='dx11_260923':return None
    if not isinstance(event.payload,bytes) or len(event.payload)<12 or struct.unpack_from('>i',event.payload,8)[0]!=16:return None
    uid=0
    try:
        uid,color=request(event.payload)
        if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None
                or s.account.store.uid!=s.account.uid or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
                or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Color session envelope or lease')
        from els_server.storage.exascale_color import perform
        return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':color-local-v1:'+str(s.account.uid)+':'+str(sequence),account_id=getattr(s.account,'account_id',None))
    except ValueError:return [acknowledgement(uid,result=2005)]
