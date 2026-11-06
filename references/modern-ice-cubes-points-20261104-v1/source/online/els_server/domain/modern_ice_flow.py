"""Selected native town entry points for shared ice points and bag withdrawals."""
from els_server.protocol import modern_ice_messages as wire

def restore(s):
    from pathlib import Path
    from els_server.domain.equipment_chip_flow import reset_authority
    from els_server.storage.modern_ice import snapshot
    account=s.account;path=Path(account.store.path).resolve();owner=account.uid;account_id=account.account_id
    session=s.shop_session_id
    def prepare(db):
        reset_authority(s)
        if s.account is not account or s.shop_session_id!=session or(s.account.uid,s.account.account_id)!=(owner,account_id):
            raise ValueError('Ice initialization selected actor changed')
    return snapshot(path,owner,account_id,prepare,initial=True)

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0xbd4,0xbd6,0xbda):return None
    kind=event.kind
    try:
        from els_server.domain.tenebros_capacity_flow import selected
        if not s.ice_test or(event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Ice request envelope')
        path,owner,account_id,prepare=selected(s)
        from els_server.storage import modern_ice as store
        if kind==0xbd6:
            if event.payload:raise ValueError('Ice bag view payload')
            return store.sort_bag(path,owner,account_id,prepare)
        if type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Ice operation sequence')
        operation=f'{s.shop_session_id}:modern-ice:{kind}:{account_id}:{owner}:{sequence}'
        action=store.claim if kind==0xbda else store.withdraw
        return action(path,owner,account_id,event.payload,operation,prepare)
    except ValueError:
        return [wire.claim(0,0,-1)]if kind==0xbda else[wire.bag(0xbd7 if kind==0xbd6 else 0xbd4,code=-1)]
