"""Route native deployment Apply only in authenticated DX11 roster phases."""
from els_server.protocol.character_selection_messages import request,ack
from els_server.storage.character_selection import save

def handle(session,event):
    if event.event_id!=0x202 or event.kind!=0xd30:return None
    valid=(session.client_build=='dx11_260923' and session.role=='game'
        and session.phase in ('characters_ready','channels_ready')
        and session.account.characters is not None and event.performers==(0,)
        and event.uid==event.target_uid==0xffffffffffffffff and event.payload_mode==0)
    if not valid:return [ack(result=-1)]
    try:
        deployed,order=request(event.payload)
        state=save(session.account.characters.path,session.account.account_id,deployed,order)
    except (ValueError,UnicodeError):return [ack(result=-1)]
    return [ack(state['deployed'],state['order'])]
