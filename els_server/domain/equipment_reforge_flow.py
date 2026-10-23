"""Authenticated town/session routing for finite core and restore operations."""
from els_server.protocol.equipment_reforge_messages import request,acknowledge,restore_ack
from els_server.domain.equipment_engrave_flow import current_lease

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x8d5,0x8d9) or not s.item_test or s.client_build!='dx11_260923':return None
    restoration=event.kind==0x8d9;target=ed=0
    try:
        if not current_lease(s):raise ValueError('Obsolete reforge lease')
        target=request(event.payload,restoration=restoration)[0]
        if (s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None
            or s.account.store.uid!=s.account.uid or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
            or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Reforge session envelope')
        ed=s.account.get_reward_balances()['ed']
        from els_server.storage.equipment_reforge import perform
        if not current_lease(s):raise ValueError('Obsolete reforge lease')
        return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':reforge-compat-v1:'+str(s.account.uid)+':'+str(sequence),restoration=restoration,account_id=s.account.account_id)
    except ValueError:return [restore_ack(result=2005) if restoration else acknowledge(target,ed,result=2005)]
