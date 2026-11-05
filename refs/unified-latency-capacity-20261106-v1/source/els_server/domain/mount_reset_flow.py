"""Original A8E mount UID request, admitted through the existing town authority."""
from els_server.protocol.mount_messages import reset_ack

def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind!=0xa8e or session.client_build!='dx11_260923' or not session.item_test:return None
    try:
        from els_server.domain.equipment_chip_flow import reset_context
        from els_server.domain.tenebros_capacity_flow import selected
        reset_context(session,event,sequence)
        path,owner,account_id,prepare=selected(session)
        from els_server.storage.mount_reset import perform
        replies=perform(path,owner,account_id,event.payload,session.shop_session_id+':mount-reset:'+str(sequence),prepare=prepare)
        session._mount_reset_rejection=None
        return replies
    except (ValueError,UnicodeError)as error:
        session._mount_reset_rejection=str(error)
        return [reset_ack(-1)]
