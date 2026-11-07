"""Type3 paid attendance in a trusted original account/character/village lease."""
from els_server.protocol import ariel_attendance_messages as wire
from els_server.storage import ariel_cash as cash,ariel_attendance as store

def authority(s):
    # Reuse the already-qualified exact Application/LocalSession/selected actor
    # graph and LOCAL worker provenance. This does not invoke any chip action.
    from els_server.domain.equipment_chip_flow import reset_authority
    reset_authority(s)
    if s.role!='game'or s.client_build!='dx11_260923'or not s.item_test or s.account.characters is None:raise ValueError('Ariel trusted current actor')

def context(s):
    authority(s)
    from els_server.domain.avatar_set_flow import context as village_context
    if not s.shop_test:raise ValueError('Ariel original shop authority')
    return village_context(s)

def validate(s,captured):
    from els_server.domain.avatar_set_flow import validate as village_validate
    authority(s);village_validate(s,captured)

def synchronization(s,events):
    events=list(events)
    if(s.client_build!='dx11_260923'or s.role!='game'or not s.item_test
       or s.account.characters is None or s.account.store is None):return events
    if not any(e.event_id==0x201 and e.kind==0x2a for e in events):
        if any(e.event_id==0x201 and e.kind in(0x4cc,0x18e)for e in events):
            from els_server.domain.ariel_attendance_mark import project
            return project(s,events)
        return events
    authority(s)
    from els_server.protocol.protocol_codec import encode_event
    guard=lambda:authority(s)
    value=store.snapshot(s.account.store.path,s.account.account_id,validate=guard)
    balance=cash.snapshot(s.account.store.path,s.account.account_id,validate=guard)
    from els_server.storage.ariel_daily_special import snapshot as daily_snapshot
    extra=[wire.wallet(balance['balance']),wire.status(value),daily_snapshot(s.account.store.path,s.account.account_id,s.account.uid,validate=guard)]
    for event in extra:encode_event(event)
    from els_server.domain.ariel_attendance_mark import project
    return project(s,events+extra)

def handle(s,event,sequence):
    if event.event_id==0x202 and event.kind==0x4cb:
        from els_server.domain.ariel_attendance_mark import handle as mark_handle
        return mark_handle(s,event,sequence)
    if event.event_id!=0x202 or event.kind not in(0x1b2,0xd78,0x1dd,0xc8c,0xc8e,0xc90):return None
    from els_server.protocol import shop_messages
    kind=event.kind
    def failure():
        if kind in(0xc8c,0xc8e,0xc90):return [wire.acknowledgement(kind,-1)]
        if kind==0x1dd:return [shop_messages.purchase_ack(-1)]
        return []
    try:
        if(event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
           or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Ariel native envelope')
        captured=context(s);guard=lambda:validate(s,captured)
        if kind==0x1b2:
            if event.payload:raise ValueError('Ariel native cash query payload')
            value=cash.snapshot(s.account.store.path,s.account.account_id,validate=guard)
            return [wire.wallet(value['balance'])]
        if kind==0xd78:
            shop_messages.catalog_request(event.payload)
            from els_server.protocol.ariel_attendance_catalog import catalog
            answer=catalog();guard();return [answer,wire.status(store.snapshot(s.account.store.path,s.account.account_id,validate=guard)),wire.wallet(cash.snapshot(s.account.store.path,s.account.account_id,validate=guard)['balance'])]
        if kind==0x1dd:
            parsed=shop_messages.purchase_request(event.payload)
            if parsed.mode is not False or parsed.option!=1:raise ValueError('Ariel purchase normal native cash selector1 only')
            request=parsed.products
        else:request=wire.request(kind,event.payload)
        def encode(db,result,state,balance):
            acknowledgement=shop_messages.purchase_ack(0,products=result['products'])if kind==0x1dd else wire.acknowledgement(kind)
            answer=[acknowledgement]+wire.inventory(result['items'],result['changed'])+[wire.wallet(balance['balance']),wire.status(state)]
            if result.get('activated'):
                from els_server.domain.ariel_attendance_mark import registered
                answer.append(registered(state))
            return answer
        return store.perform(s.account.store.path,s.account.account_id,s.account.uid,s.shop_session_id,sequence,kind,event.payload,request,validate=guard,encode=encode)
    except ValueError:return failure()
