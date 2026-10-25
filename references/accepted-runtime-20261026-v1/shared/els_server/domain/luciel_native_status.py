"""Persist the native battle38E active selector under existing actor/run leases."""
def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x38e:return None
    # Other phases' periodic status remains ignored, including native loading reset.
    if s.phase!='dungeon_active':return []
    from els_server.domain.luciel_state import active_context,validate_active_context,prepare_active
    from els_server.storage.luciel_native_status import perform
    try:
        if (event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
            or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('LuCiel status envelope')
        captured=active_context(s,0x4e2)
        result=perform(s.account.store.path,s.account.uid,event.payload,
            account_id=s.account.account_id,session_id=s.shop_session_id,epoch=s.reward_run_id,sequence=sequence,
            validate=lambda:validate_active_context(s,0x4e2,captured),
            prepare=lambda reply:prepare_active(s,0x4e2,captured,reply))
    except ValueError:return []
    prepared=result['prepared']
    if prepared is not None:
        # No self4E3 acknowledgement: native38E is a periodic status report.
        assert prepared['room'] is None and prepared['own'] is None
        for other,mailbox in prepared['mailboxes']:other.mailbox=mailbox
    return []
