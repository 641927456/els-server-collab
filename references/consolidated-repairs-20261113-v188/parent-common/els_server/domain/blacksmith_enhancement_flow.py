"""Narrow smith5FF route with frozen actor binding before/after SQL wait."""
import sqlite3
from els_server.protocol.protocol_codec import Event
from els_server.protocol.blacksmith_enhancement_messages import acknowledgement
from els_server.domain.manufacture_flow import _actor,_binding,_same_binding

def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x5ff:return None
    try:
        def context():
            return bool(_actor(session) and type(sequence) is int and 1<=sequence<2**32
                and event.performers in ((),(0,)) and event.uid==event.target_uid==2**64-1 and event.payload_mode==0)
        if not context():raise ValueError('Smith enhancement session envelope')
        binding=_binding(session)
        def authorize():return bool(context() and _same_binding(session,binding))
        def prepare_replay(response):return [*response,session.saved_user_sync()]
        from els_server.storage.blacksmith_enhancement import enhance
        return enhance(binding[6],binding[4],event.payload,f'{binding[7]}:{binding[4]}:smith-enhance:{sequence}',
            account_id=binding[5],authorize=authorize,prepare_replay=prepare_replay)
    except (ValueError,sqlite3.Error):
        return [Event(0x201,kind=0x600,payload=acknowledgement(result=-1))]
