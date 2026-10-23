"""Town-only native sphere route with current actor and save binding."""
import sqlite3
from els_server.domain.manufacture_flow import _actor,_binding,_same_binding
from els_server.protocol.hunter_sphere_messages import acknowledgement
from els_server.protocol.protocol_codec import Event

def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x705:return None
    try:
        def context():
            return bool(_actor(session)and type(sequence)is int and 1<=sequence<2**32 and event.performers in ((),(0,))
                and event.uid==event.target_uid==2**64-1 and event.payload_mode==0)
        if not context():raise ValueError('Sphere actor envelope')
        binding=_binding(session)
        def authorize():return bool(context()and _same_binding(session,binding))
        def replay(response):return [*response,session.saved_user_sync()]
        from els_server.storage.hunter_sphere import convert
        return convert(binding[6],binding[4],binding[5],event.payload,f'{binding[7]}:{binding[4]}:hunter-sphere:{sequence}',authorize=authorize,prepare_replay=replay)
    except (ValueError,sqlite3.Error):return [Event(0x201,kind=0x706,payload=acknowledgement(result=-1))]
