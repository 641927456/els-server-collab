"""Authenticated mode2 fill / mode4 apply for mystic weapon columns."""
from els_server.domain.equipment_engrave_flow import current_lease

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x6e7 or not s.item_test or s.client_build!='dx11_260923':return None
    payload=event.payload
    if not isinstance(payload,bytes) or len(payload)<18:return None
    from els_server.protocol.artifact_socket_messages import request,acknowledgement
    try:
        uid,groups,flag,mode=request(payload)
    except ValueError:
        return None
    if mode not in (2,4):return None
    if mode==2 and (len(payload)<38 or len(groups)!=1 or next(iter(groups)) not in (9,10,11,12)):return None
    if mode==4 and groups:return None
    ed=0
    try:
        if not current_lease(s):raise ValueError('Obsolete spell lease')
        if (s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None
                or s.account.store.uid!=s.account.uid or type(sequence) is not int or not 1<=sequence<2**32
                or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            raise ValueError('Spell session envelope')
        ed=s.account.get_reward_balances()['ed']
        operation=s.shop_session_id+':spell-socket:'+str(s.account.uid)+':'+str(sequence)
        if not current_lease(s):raise ValueError('Obsolete spell lease')
        if mode==4:
            from els_server.storage.spell_socket import confirm
            return confirm(s.account.store.path,s.account.uid,uid,operation,
                           account_id=getattr(s.account,'account_id',None))
        from els_server.storage.spell_socket import perform
        return perform(s.account.store.path,s.account.uid,payload,operation,
                       account_id=getattr(s.account,'account_id',None))
    except ValueError:
        return [acknowledgement(uid,ed,(),mode=mode,option=0,result=-1)]
