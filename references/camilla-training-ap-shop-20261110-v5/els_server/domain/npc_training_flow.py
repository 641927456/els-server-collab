"""Camilla's free training uses a client-owned room and the normal town return."""
import math
import struct
from els_server.domain.camilla_force import CAMILLA_TOWNS
from els_server.domain.housing_access_flow import capture
from els_server.protocol.dungeon_messages import begin_substage,end_ack,initial_part,initial_substage
from els_server.protocol.npc_training_messages import acknowledgement,TRAINING_TEMPLATE
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.pvp_loading_messages import progress_request,progress_ack,progress_notice

def _envelope(event,sequence):
    return (event.performers in((),(0,)) and event.uid==event.target_uid==2**64-1
        and event.payload_mode==0 and type(sequence)is int and 1<=sequence<2**32)


def handle(s,event,sequence):
    if event.event_id!=0x202:return None
    returning=getattr(s,'_npc_training_return',None)
    if returning is not None and event.kind in (0x67,0x91,0xb3,0x192,0x225):
        account,session,town,stage=returning
        owned=(account is s.account and session==s.shop_session_id and _envelope(event,sequence)
               and account.get_location()['map']==town)
        if event.kind==0x225:
            if owned and event.payload==struct.pack('>iB',town,0):return None
            return [Event(0x201,kind=0x226,payload=struct.pack('>5i',515,town,0,0,0))]
        if not owned or s.phase!='map_loading':return []
        if event.kind==0x192:
            # 31B8010 sends a bool when the native training settings change.
            if stage!='active' or event.payload not in (b'\0',b'\1'):return []
            return [Event(0x201,kind=0x193,payload=bytes(4))]
        if event.kind==0x67:
            if not 100<=len(event.payload)<=8192 or event.payload[:4]!=struct.pack('>i',0x72):return []
            if stage=='returning':return [end_ack()]
            if stage!='active':return []
            reply=[end_ack(),s.saved_user_sync()]
            s._npc_training_return=(account,session,town,'returning')
            s.pending_map=None
            s.dungeon_return_pending=True
            s.inventory_town_sync_sent=True
            return reply
        if event.kind==0xb3:
            if stage not in ('substage','active') or len(event.payload)!=9 or event.payload[:5]!=bytes(5):return []
            value=struct.unpack_from('>f',event.payload,5)[0]
            if not math.isfinite(value) or not 0<=value<=1e9:return []
            reply=[Event(0x201,kind=0xb4,payload=bytes(4)),
                   Event(0x201,kind=0xb5,payload=struct.pack('>iQ',0,account.uid))]
            if stage=='substage':
                s._npc_training_return=(account,session,town,'active')
                reply.extend((Event(0x201,kind=0xb6,payload=bytes(16)),initial_part(),begin_substage()))
            return reply
        try:progress=progress_request(event.payload)
        except ValueError:return []
        reply=[progress_ack(progress),progress_notice(account.uid,progress)]
        if progress==100 and stage=='loading':
            s._npc_training_return=(account,session,town,'substage')
            # C2BCD0 reads B2 before the original client can load part zero.
            # Free training begins with empty population maps.
            reply.extend((Event(0x201,kind=0x96,payload=b''),initial_substage()))
        return reply
    if event.kind!=0x18f:return None
    try:same,_=capture(s)
    except ValueError:return []
    account=s.account
    allowed=(_envelope(event,sequence)and event.payload==struct.pack('>i',TRAINING_TEMPLATE)
        and s.active_map in CAMILLA_TOWNS and s.dungeon_run is None)
    character=account.character()
    snapshot=account.get_inventory_snapshot(equipped_only=True)
    response=acknowledgement(character,account.get_skills(),snapshot['items'],s.port_probe_port,
        result=0 if allowed else -1)
    encode_event(response)
    if not same():return []
    if allowed:
        s._npc_training_return=(account,s.shop_session_id,s.active_map,'loading')
        s.phase='map_loading'
        s.completed.difference_update((0x225,0x227))
    return [response]
