"""Authenticated town/session routing for finite core and restore operations."""
from els_server.protocol.equipment_reforge_messages import request,acknowledge,restore_ack
from els_server.domain.equipment_engrave_flow import current_lease

def handle(s,event,sequence):
    if event.event_id==0x202 and event.kind==0xa22 and s.item_test and s.client_build=='dx11_260923':
        from els_server.protocol.reforge_scroll_messages import acknowledgement,request as scroll_request
        from els_server.storage.reforge_scroll import perform as apply_scroll
        actor=s.account;store=actor.store;shop=s.shop_session_id
        def prepare():
            from els_server.domain.equipment_chip_flow import reset_authority
            reset_authority(s)
            if (not current_lease(s) or s.account is not actor or actor.store is not store or s.shop_session_id!=shop
                or s.role!='game' or s.phase!='town_ready' or actor.characters is None or store is None or store.uid!=actor.uid
                or type(sequence)is not int or not 0<sequence<2**32 or event.performers not in((),(0,))
                or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Reforge scroll current actor')
        try:
            prepare();scroll_request(event.payload)
            return apply_scroll(store.path,actor.uid,actor.account_id,event.payload,shop+':reforge-scroll:'+str(actor.uid)+':'+str(sequence),prepare=prepare)
        except ValueError:return[acknowledgement(result=2005)]
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
