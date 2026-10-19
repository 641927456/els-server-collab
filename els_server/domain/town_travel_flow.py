"""Bind the ordinary native58C success to its225/227 destination."""
import struct,time,uuid
from els_server.protocol.protocol_codec import Event
from els_server.protocol import town_travel_messages as wire

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x58c:return None
    if not (s.enter_town and s.item_test and s.client_build=='dx11_260923' and s.account.characters is not None):return []
    destination=struct.unpack_from('>i',event.payload)[0] if len(event.payload)>=4 else 0
    def failure():return [wire.acknowledgement(destination,s.account.get_reward_balances()['ed'],result=-1)]
    if (event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0
        or type(sequence) is not int or not 0<=sequence<2**64 or s.role!='game'):return failure()
    pending=getattr(s,'town_warp_transition',None)
    if pending is not None:
        if pending['payload']==event.payload and pending['sequence']==sequence and s.phase in ('map_loading','square_accepted'):
            return [Event(0x201,kind=0x58d,payload=pending['response'])]
        return failure()
    if s.phase!='town_ready' or s.dungeon_return_pending:return failure()
    source=s.account.get_location()['map']
    if s.active_map!=source:return failure()
    try:
        wire.request(event.payload)
        from els_server.storage.town_travel import travel
        operation=str(uuid.uuid5(uuid.UUID(s.shop_session_id),f'town-warp:{s.account.uid}:{sequence}'))
        result=travel(s.account.store.path,s.account.uid,s.account.account_id,source,event.payload,operation,now=int(time.time()))
    except (ValueError,OverflowError):return failure()
    with s.account.lock:s.account.location=s.account.store.load()
    s.town_warp_transition=dict(destination=destination,payload=event.payload,sequence=sequence,response=result['response'],operation=operation)
    s.phase='map_loading';s.pending_map=None;s.inventory_town_sync_sent=False
    return [Event(0x201,kind=0x58d,payload=result['response'])]
