"""Answer the native battlefield-join request in a solo profile.

0x374 is only owned by FieldBosses, which exists in the friends world. A local
profile has no world, so the request fell through unanswered and the client
stayed on the join screen with its field tick stopped. Reply with the codec's
own refusal instead of silence.
"""
from els_server.protocol import field_boss_messages as wire


def handle(session,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x374:return None
    if getattr(session,'application',None) is not None:return None
    if getattr(session,'role',None)!='game' or getattr(session,'client_build',None)!='dx11_260923':return None
    return [wire.joined((),None,0,result=-1)]
