"""Dispatch only the native other-character bank browser, leaving transfers alone."""
from els_server.protocol.bank_view_messages import acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.bank_view import contents


def handle(session,event):
    if not (session.item_test and session.client_build=='dx11_260923' and
            event.event_id==0x202 and event.kind==0x72e):return None
    failed=[Event(0x201,kind=0x72f,payload=acknowledgement(result=-1))]
    if session.role!='game' or session.phase!='town_ready' or session.account.characters is None:return failed
    try:return contents(session.account.store.path,session.account.uid,event.payload)
    except ValueError:return failed
