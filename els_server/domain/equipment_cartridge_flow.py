"""Complete native failure acknowledgements for unqualified cartridge operations.

The client owns the UI and its waiting state. Equip, removal and growth remain unavailable. Finite registration is separately
qualified for existing singleton stock under account sharing and live actor checks.
No collection initialization, SQL mutation, charge or success is manufactured.
"""
from els_server.protocol.equipment_cartridge_messages import acknowledge, request

REQUEST_KINDS = frozenset((0xd4e, 0xd50, 0xd52, 0xd54))


def _session(s):
    from els_server.domain.equipment_engrave_flow import current_lease
    from els_server.domain.equipment_chip_flow import reset_authority
    reset_authority(s) # Existing exact normal App/root/save/UUID identity guard; no reset operation.
    if (not current_lease(s) or getattr(s,'released',False) or s.role!='game' or s.phase!='town_ready'
            or s.client_build!='dx11_260923' or not s.item_test
            or s.account.characters is None or s.account.store is None
            or s.account.store.uid!=s.account.uid or not {0x28,0x225,0x227}<=s.completed):
        raise ValueError('Cartridge current selected town actor required')
    return s.account.store.path,s.account.uid,s.account.account_id


def _selected_authorizer(s,selection):
    # Recheck the captured selected actor, not just the connection's lease.
    account=s.account;store=account.store;root=getattr(account,'root',None)
    identity=getattr(s,'identity',None);operation_root=s.shop_session_id
    app=getattr(s,'application',None);local_app=getattr(s,'_chip_reset_local_application',None)
    def authorize():
        try:
            return (s.account is account and s.account.store is store
                    and getattr(s.account,'root',None)is root
                    and getattr(s,'identity',None)is identity
                    and getattr(s,'application',None)is app
                    and getattr(s,'_chip_reset_local_application',None)is local_app
                    and s.shop_session_id==operation_root and _session(s)==selection)
        except (ValueError,AttributeError,TypeError):return False
    return authorize


def _register(s,event,sequence):
    try:
        path,owner,account_id=_session(s)
        request(0xd4e,event.payload)
        if (type(sequence)is not int or not 1<=sequence<2**32
                or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
            raise ValueError('Cartridge registration envelope')
        from els_server.storage.account_cartridge_registration import perform
        authorize=_selected_authorizer(s,(path,owner,account_id))
        operation=s.shop_session_id+':cartridge-register-v1:'+str(account_id)+':'+str(owner)+':'+str(sequence)
        return perform(path,owner,account_id,event.payload,operation,authorize=authorize)
    except ValueError:
        # Native nonzero-result branch does not apply the empty map/points.
        return [acknowledge(0xd4f,result=2005,identity=0,rows={},points=0)]


def synchronize(s,messages):
    # Own errors must never discard unrelated periodic packets or mark sent.
    if (s.role!='game' or s.phase!='town_ready' or s.client_build!='dx11_260923'
            or not s.item_test or s.account.store is None or s.account.characters is None):return messages
    try:
        path,owner,account_id=_session(s)
        from els_server.storage.account_cartridge_registration import snapshot
        authorize=_selected_authorizer(s,(path,owner,account_id))
        from els_server.protocol.equipment_cartridge_messages import state
        from els_server.protocol.protocol_codec import encode_event
        current=snapshot(path,owner,account_id,authorize=authorize)
        key=(account_id,owner,current['revision'])
        if getattr(s,'cartridge_sync_key',None)==key:return messages
        notice=state(current['rows'],current['points']);encode_event(notice)
        if not authorize():raise ValueError('Obsolete Cartridge notification selection')
        s.cartridge_sync_key=key;s.cartridge_sync_error=None
        return [*messages,notice]
    except Exception as exc:
        s.cartridge_sync_error=type(exc).__name__
        return messages


def handle(s, event, sequence):
    if (event.event_id != 0x202 or event.kind not in REQUEST_KINDS
            or s.client_build != 'dx11_260923'):
        return None
    if event.kind==0xd4e:return _register(s,event,sequence)
    identity = 0
    ed = 0
    try:
        fields = request(event.kind, event.payload)
        if (s.role != 'game' or s.phase != 'town_ready'
                or not s.item_test or s.account.characters is None
                or s.account.store is None
                or type(sequence) is not int or not 1 <= sequence < 2**32
                or event.performers not in ((), (0,))
                or event.uid != 0xffffffffffffffff
                or event.target_uid != 0xffffffffffffffff
                or event.payload_mode != 0):
            raise ValueError('Cartridge session envelope')
        if event.kind == 0xd50:
            identity = fields[1]
        elif event.kind == 0xd54:
            identity = fields[0]
        # The initialized selected actor already owns this balance. On the
        # native nonzero-result branch neither ED nor the empty map is applied.
        if event.kind == 0xd54:
            ed = s.account.get_reward_balances()['ed']
    except ValueError:
        identity = 0
    kind = event.kind + 1
    extras = {'points': 0} if kind in (0xd4f, 0xd55) else {}
    if kind == 0xd55:
        extras['ed'] = ed
    return [acknowledge(kind, result=2005, identity=identity, rows={}, **extras)]
