"""Original coupon->cash order->ordinary withdrawal; client owns the UI."""


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in(0x1a0,0xd7a,0xd7c):return None
    if (s.client_build!='dx11_260923' or not s.shop_test or s.role!='game'
            or type(sequence)is not int or not 1<=sequence<2**32
            or event.performers!=(0,)or event.uid!=2**64-1 or event.target_uid!=2**64-1
            or event.payload_mode!=0):return []
    from els_server.protocol import coupon_messages as wire
    from els_server.storage import coupon_codes as store
    from els_server.domain.avatar_set_flow import context,validate as validate_context
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    try:
        captured=context(s)
        def validate():
            validate_context(s,captured)
            if not current_lease(s):raise ValueError('Coupon current lease')
            app=getattr(s,'application',None)
            if app is None or not app.registry.enabled(s.account.account_id):
                raise ValueError('Coupon authenticated account')
        validate()
    except ValueError:return []
    path=s.account.store.path;account=s.account.account_id;owner=s.account.uid
    if event.kind==0x1a0:
        try:text=wire.redeem_request(event.payload)
        except ValueError:return []
        try:return [store.redeem(path,text,account,owner,validate=validate,encode=lambda:wire.redeem_ack(0))]
        except ValueError:return [wire.redeem_ack(940)]
    if event.kind==0xd7a:
        try:
            page=wire.deposit_request(event.payload)
            return [store.deposit(path,account,owner,page,validate=validate,encode=wire.deposit_ack)]
        except ValueError:return [wire.deposit_ack(result=-1)]
    def withdrawal_response(items,db):
        from els_server.storage.resurrection_counter import count
        return wire.withdrawal_ack(items,0,resurrection_count=count(db,owner))
    try:
        trans,product=wire.withdrawal_request(event.payload)
        return [store.withdraw(path,account,owner,trans,product,s.shop_session_id,sequence,
                               validate=validate,encode=withdrawal_response)]
    except ValueError:return [wire.withdrawal_ack(result=-1)]
