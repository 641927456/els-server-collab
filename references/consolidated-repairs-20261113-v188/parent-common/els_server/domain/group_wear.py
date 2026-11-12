"""Commit-bound peer equipment and native owner-state replication."""
import math,struct,uuid
from els_server.protocol.protocol_codec import Event

def envelope(s,event):
    from els_server.domain.equipment_chip_flow import current_lease
    if (s.client_build!='dx11_260923' or s.role!='game' or not current_lease(s)
        or event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=2**64-1
        or event.payload_mode!=0):raise ValueError('Group wear support envelope')

def capability(s,event):
    envelope(s,event)
    # Pure support state is recorded/revoked on the existing canonical game
    # lease, including loading. Actual equipment changes retain membership's
    # strict active-room/stage gates below.
    if len(event.payload)!=9:raise ValueError('Group wear capability size')
    s.group_wear_support=(s.account,s.account.uid,s.shop_session_id) if event.kind==0xff20 else None
    if event.kind==0xff21:s.group_wear_pending=None

def membership(s,room):
    from els_server.domain.equipment_chip_flow import current_lease
    app=s.application;dungeons=app.world.dungeons
    if (room.phase!='active' or room.party.get('run') is not room
        or len(room.members)<2 or s not in room.members
        or s.dungeon_participants!=frozenset(p.account.uid for p in room.members)):
        raise ValueError('Group wear room not active')
    state=[]
    for peer in room.members:
        if (not current_lease(peer) or peer.released or peer.social_overflow or peer.coop_error
            or dungeons.room(peer) is not room or app.world.party_of.get(peer) is not room.party
            or peer not in room.party['members'] or peer.phase!='dungeon_active'
            or not peer.dungeon_substage_synced or peer.gate_stage_loading
            or peer.dungeon_return_pending or peer.dungeon_failed or peer.clear_notified
            or peer.part_end_notified or peer.dungeon_end_payload is not None
            or peer.dungeon_id!=room.identity or peer.gate_stage!=s.gate_stage
            or getattr(peer.dungeon_run,'part',None)!=getattr(s.dungeon_run,'part',None)
            or peer.dungeon_participants!=s.dungeon_participants
            or getattr(peer,'group_wear_support',None)!=(peer.account,peer.account.uid,peer.shop_session_id)):
            raise ValueError('Group wear member not ready or support missing')
        state.append((peer,peer.account,peer.account.uid,peer.shop_session_id,peer.reward_run_id,
            peer.gate_stage,getattr(peer.dungeon_run,'part',None)))
    return (room.seed,tuple(state))

def prepare(s,captured,changes,character):
    if s.phase!='dungeon_active':return ()
    room=captured[4]
    if room is None:return ()
    from els_server.domain.fashion_state import move_ack
    from els_server.domain.tutorial_accessory import validate_wear_context
    validate_wear_context(s,captured,dungeon=True)
    pending=getattr(s,'group_wear_pending',None)
    if pending is not None and pending[1]==captured:
        raise ValueError('Previous group wear native state not received')
    worn=tuple((position,item) for position,item in changes if position[0]==9)
    if not worn:return ()
    epoch=uuid.UUID(room.seed)
    if epoch.version!=4 or str(epoch)!=room.seed:raise ValueError('Group wear room generation')
    token=uuid.uuid4().bytes;delta=move_ack(worn)
    peers=tuple(peer for peer in room.members if peer is not s)
    # Reserve room for the exact forthcoming marked106. Check before SQL commit.
    for peer in peers:
        mailbox=peer.mailbox
        if len(mailbox.messages)+len(mailbox.moves)>=256 or mailbox.bytes+86+len(delta)>256*1024:
            raise ValueError('Group wear peer consumer full')
    return ((token,captured,epoch.bytes,s.account.uid,peers,delta),)

def deliver(s,publications):
    if not publications:return ()
    if len(publications)!=1:raise ValueError('Group wear commit publication count')
    pending=publications[0];s.group_wear_pending=pending
    token,captured,room,uid,peers,delta=pending
    return (Event(0x201,kind=0x106,payload=bytes((0x82,3))+token+room+struct.pack('>Q',uid)),)

def report(s,event):
    envelope(s,event)
    wire=event.payload
    if len(wire)!=101 or wire[0]!=3:raise ValueError('Group wear native report size/version')
    token=wire[1:17];pending=getattr(s,'group_wear_pending',None)
    previous=getattr(s,'group_wear_report_receipt',None)
    if previous is not None and previous[0]==token:
        if previous[1]!=wire:raise ValueError('Conflicting group wear native report replay')
        return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\0')
    if pending is None or pending[0]!=token:raise ValueError('Group wear native report has no committed token')
    token,captured,room,uid,peers,delta=pending
    if wire[17:41]!=room+struct.pack('>Q',uid):raise ValueError('Group wear native report owner/room')
    values=struct.unpack('>15f',wire[41:])
    if (not all(math.isfinite(v) and v>=0 for v in values) or values[0]<=0 or values[7]<=0
        or values[14]>4294967040):
        raise ValueError('Group wear native report numeric inputs')
    from els_server.domain.tutorial_accessory import validate_wear_context
    try:validate_wear_context(s,captured,dungeon=True)
    except ValueError:
        # The already committed inventory is never rolled back. A room/stage,
        # peer or support transition retires this obsolete replication request.
        s.group_wear_pending=None
        return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\1')
    payload=bytes((0x81,3))+room+struct.pack('>Q',uid)+wire[41:97]+wire[97:101]+delta
    for peer in peers:
        mailbox=peer.mailbox
        if len(mailbox.messages)+len(mailbox.moves)>=256 or mailbox.bytes+len(payload)>256*1024:
            raise ValueError('Group wear peer consumer full')
    message=Event(0x201,kind=0x106,payload=payload)
    for peer in peers:s.application.world.send(peer,message)
    s.group_wear_pending=None;s.group_wear_report_receipt=(token,wire)
    return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\0')
