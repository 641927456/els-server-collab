"""Authenticated native971 dispatch, first red-column subset only."""
from els_server.protocol.equipment_spell_exchange import request,acknowledgement

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x971 or not s.item_test or s.client_build!='dx11_260923':return None
    try:
        request(event.payload)
        if (s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None
                or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
                or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            raise ValueError('Mystic exchange session envelope')
        from els_server.storage.equipment_spell_exchange import perform
        return perform(s.account.store.path,s.account.uid,event.payload,
            s.shop_session_id+':mystic-red-exchange-v1:'+str(s.account.uid)+':'+str(sequence))
    except ValueError:return [acknowledgement(result=2005)]
