"""Authenticated circuit mode16 dispatch before the shared artifact parser."""
import struct
from els_server.protocol.equipment_circuit_messages import request,acknowledgement
from els_server.domain.equipment_engrave_flow import current_lease


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x6e7 or not s.item_test or s.client_build!='dx11_260923':return None
    if not isinstance(event.payload,bytes) or len(event.payload)<6 or struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]!=16:return None
    uid=0;ed=0
    try:
        if not current_lease(s):raise ValueError('Obsolete circuit lease')
        uid,slots,flag=request(event.payload)
        if (s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None
                or s.account.store.uid!=s.account.uid or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
                or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            raise ValueError('Circuit session envelope')
        ed=s.account.get_reward_balances()['ed']
        from els_server.storage.equipment_circuits import perform
        if not current_lease(s):raise ValueError('Obsolete circuit lease')
        return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':circuit-compat-v1:'+str(s.account.uid)+':'+str(sequence),account_id=getattr(s.account,'account_id',None))
    except ValueError:return [acknowledgement(uid,ed,result=2005)]
