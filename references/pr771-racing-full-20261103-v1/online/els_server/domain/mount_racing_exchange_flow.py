"""Current town actor and native Camilla223 entry."""
import struct
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.fish_exchange_messages import acknowledgement


def handle(s,event,sequence):
    if (event.event_id!=0x202 or event.kind!=0x223 or len(event.payload)<16
            or struct.unpack_from('>i',event.payload)[0]!=40016
            or struct.unpack_from('>i',event.payload,12)[0]!=714109):return None
    from els_server.domain.equipment_chip_flow import reset_context
    from els_server.domain.tenebros_capacity_flow import selected
    # Capture the selected actor before constructing either a success or an
    # absolute-wallet rejection. An obsolete connection receives no projection.
    try:path,owner,account_id,prepare=selected(s)
    except ValueError:return []
    try:
        reset_context(s,event,sequence)
        from els_server.storage.mount_racing_exchange import exchange
        replies=exchange(path,owner,account_id,s.active_map,event.payload,
            s.shop_session_id+':racing-crystal:'+str(sequence),prepare=prepare)
        s._mount_exchange_rejection=None
        return replies
    except ValueError as error:
        s._mount_exchange_rejection=str(error)
        prepare(None)
        answer=Event(0x201,kind=0x224,payload=acknowledgement(s.account.get_reward_balances()['ed'],result=-1,exchange_type=1))
        encode_event(answer);prepare(None)
        return [answer]
