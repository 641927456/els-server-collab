"""Dedicated current-town normal9ED; no ticket/source/GUI/client behavior is invented."""
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol.equipment_reforge_transfer_messages import request,acknowledge


def _session(s):
    account=getattr(s,'account',None)
    return bool(current_lease(s)and s.role=='game'and s.phase=='town_ready'and account is not None
        and account.characters is not None and account.store is not None and account.store.uid==account.uid)


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x9ed or not s.item_test or s.client_build!='dx11_260923':return None
    # Malformed bytes cannot supply a legal dualUID acknowledgement. Reject without mutation.
    try:source,target,flag=request(event.payload)
    except ValueError:return []
    ed=0
    try:
        if (not _session(s)or type(sequence)is not int or not 1<=sequence<2**32
                or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Transfer session/envelope')
        ed=s.account.get_reward_balances()['ed']
        from els_server.storage.equipment_reforge_transfer import perform
        return perform(s.account.store.path,s.account.uid,event.payload,
            s.shop_session_id+':reforge-transfer-keep-each-life-compat-v1:'+str(s.account.uid)+':'+str(sequence),
            account_id=s.account.account_id,authorize=lambda:_session(s))
    except ValueError:return [acknowledge(source,target,ed,result=2005)]
