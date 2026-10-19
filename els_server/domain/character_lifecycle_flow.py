"""Account-bound character lifecycle in authenticated DX11 roster phases."""
from els_server.protocol.character_lifecycle_messages import request,schedule_ack,restore_ack,finalize_ack
from els_server.storage.character_lifecycle import change,LifecycleError
def handle(session,event):
    kinds={0x48a:('schedule',schedule_ack),0x598:('restore',restore_ack),0x59a:('finalize',finalize_ack)}
    if event.event_id!=0x202 or event.kind not in kinds:return None
    operation,reply=kinds[event.kind];uid=0
    valid=(session.client_build=='dx11_260923' and session.role=='game' and session.phase in ('characters_ready','channels_ready') and session.account.characters is not None and event.performers==(0,) and event.uid==event.target_uid==0xffffffffffffffff and event.payload_mode==0)
    if not valid:return [reply(result=1)]
    try:
        uid=request(event.payload,allow_opaque=operation!='schedule');result=change(session.account.characters.path,session.account.account_id,uid,operation)
    except (ValueError,UnicodeError) as error:
        kw=dict(uid=uid,result=getattr(error,'result',1))
        if operation=='schedule':kw['error_until']=getattr(error,'until',0)
        else:kw['until']=getattr(error,'until',0)
        return [reply(**kw)]
    if operation=='finalize':
        from els_server.storage.character_selection import snapshot
        state=snapshot(session.account.characters.path,session.account.account_id)
        # Drop any cached role facade. Storage rejects subsequent access to the
        # tombstone, including stale create receipts and character-entry packets.
        session.account.root.character_accounts.pop(uid,None)
        return [reply(uid,selection=state)]
    if operation=='schedule':return [reply(uid,until=result['until'],restore_at=result['restore_at'])]
    return [reply(uid,until=result['until'])]
