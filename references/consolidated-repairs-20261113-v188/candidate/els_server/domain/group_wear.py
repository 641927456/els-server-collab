"""Commit-bound peer equipment and native owner-state replication."""
import math,struct,uuid
from els_server.protocol.protocol_codec import Event

class NotReady(ValueError):pass

def _title(delta):
    return struct.unpack('>i',delta[1:])[0] if len(delta)==5 and delta[0]==2 else None

def _retire(s,pending):
    s.group_wear_obsolete=(pending[0],pending[2],pending[3]);s.group_wear_pending=None
    title=_title(pending[5])
    if title is not None:s.group_title_dirty=((s.account,s.account.uid,s.shop_session_id),title)

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
    lease=(s.account,s.account.uid,s.shop_session_id)
    s.group_wear_support=lease if event.kind in (0xff20,0xff23) else None
    s.group_title_support=lease if event.kind==0xff23 else None
    if event.kind in (0xff21,0xff24):
        pending=getattr(s,'group_wear_pending',None)
        if pending is not None:_retire(s,pending)

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
            or dungeons.room(peer) is not room or app.world.party_of.get(peer) is not room.owner_party
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
    worn=tuple((position,item) for position,item in changes if position[0]==9)
    if not worn:return ()
    return _prepare(s,captured,move_ack(worn))


def prepare_title(s,captured,title,*,replace=False):
    room=captured[4]
    if room is None:return ()
    if any(getattr(m,'group_title_support',None)!=(m.account,m.account.uid,m.shop_session_id) for m in room.members):
        raise NotReady('Party title support not loaded')
    return _prepare(s,captured,b'\2'+struct.pack('>i',title),replace_title=replace)


def observe_title(s,previous,active):
    """Publish authoritative title changes once this room can consume them."""
    lease=(s.account,s.account.uid,s.shop_session_id)
    pending=getattr(s,'group_wear_pending',None)
    dirty=getattr(s,'group_title_dirty',None)
    if dirty is not None and dirty[0]!=lease:s.group_title_dirty=None
    pending_title=_title(pending[5])if pending is not None else None
    if (previous!=active or pending_title is not None and pending_title!=active[1]
        or getattr(s,'group_title_dirty',None)is not None):
        s.group_title_dirty=(lease,active[1])
    dirty=getattr(s,'group_title_dirty',None)
    app=getattr(s,'application',None)
    if s.phase!='dungeon_active' or app is None or app.world.dungeons.room(s)is None:
        s.group_title_dirty=None
        return ()
    if dirty is None:return ()
    from els_server.domain.tutorial_accessory import wear_context
    try:captured=wear_context(s,dungeon=True)
    except ValueError:return ()  # The room/member stage is not ready yet.
    if pending is not None and pending[1]==captured and pending_title==dirty[1]:
        s.group_title_dirty=None
        return ()
    # Finish an equipment delta first; its item changes cannot be replaced
    # by a title-only notification. The dirty title survives until then.
    if pending is not None and pending[1]==captured and pending_title is None:return ()
    try:publications=prepare_title(s,captured,dirty[1],replace=True)
    except NotReady:return ()
    return deliver(s,publications)


def _prepare(s,captured,delta,*,replace_title=False):
    room=captured[4]
    from els_server.domain.tutorial_accessory import validate_wear_context
    validate_wear_context(s,captured,dungeon=True)
    pending=getattr(s,'group_wear_pending',None)
    if pending is not None and pending[1]==captured and not(replace_title and _title(pending[5])is not None):
        raise NotReady('Previous group wear native state not received')
    epoch=uuid.UUID(room.seed)
    if epoch.version!=4 or str(epoch)!=room.seed:raise ValueError('Group wear room generation')
    token=uuid.uuid4().bytes
    peers=tuple(peer for peer in room.members if peer is not s)
    # Reserve room for the exact forthcoming marked106. Check before SQL commit.
    for peer in peers:
        mailbox=peer.mailbox
        if len(mailbox.messages)+len(mailbox.moves)>=256 or mailbox.bytes+86+len(delta)>256*1024:
            raise NotReady('Group wear peer consumer full')
    return ((token,captured,epoch.bytes,s.account.uid,peers,delta),)

def deliver(s,publications):
    if not publications:return ()
    if len(publications)!=1:raise ValueError('Group wear commit publication count')
    pending=publications[0]
    old=getattr(s,'group_wear_pending',None)
    if old is not None:s.group_wear_obsolete=(old[0],old[2],old[3])
    s.group_wear_pending=pending
    token,captured,room,uid,peers,delta=pending
    title=_title(delta)is not None
    if title:s.group_title_dirty=None
    return (Event(0x201,kind=0x106,payload=bytes((0x84 if title else 0x82,3))+token+room+struct.pack('>Q',uid)+(delta[1:]if title else b'')),)

def report(s,event):
    envelope(s,event)
    wire=event.payload
    if len(wire)!=101 or wire[0]!=3:raise ValueError('Group wear native report size/version')
    token=wire[1:17];pending=getattr(s,'group_wear_pending',None)
    obsolete=getattr(s,'group_wear_obsolete',None)
    if obsolete is not None and token==obsolete[0]:
        if wire[17:41]!=obsolete[1]+struct.pack('>Q',obsolete[2]):raise ValueError('Obsolete group wear report owner/room')
        return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\1')
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
        _retire(s,pending)
        return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\1')
    title=_title(delta)is not None
    if title:
        from els_server.storage import titles
        from els_server.storage.read_scope import snapshot_connection
        with snapshot_connection(s.account.store.path)as db:
            db.execute('BEGIN');current=titles.equipped(db,s.account.uid)
        committed=struct.unpack('>i',delta[1:])[0]
        if current!=committed:
            _retire(s,pending)
            notices=observe_title(s,(s.account.uid,committed),(s.account.uid,current))
            for notice in notices:s.application.world.send(s,notice)
            return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\1')
    if title and any(getattr(m,'group_title_support',None)!=(m.account,m.account.uid,m.shop_session_id)for m in (s,*peers)):
        _retire(s,pending)
        return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\1')
    payload=bytes((0x85 if title else 0x81,3))+room+struct.pack('>Q',uid)+wire[41:97]+wire[97:101]+(delta[1:]if title else delta)
    for peer in peers:
        mailbox=peer.mailbox
        if len(mailbox.messages)+len(mailbox.moves)>=256 or mailbox.bytes+len(payload)>256*1024:
            raise ValueError('Group wear peer consumer full')
    message=Event(0x201,kind=0x106,payload=payload)
    for peer in peers:s.application.world.send(peer,message)
    s.group_wear_pending=None;s.group_wear_report_receipt=(token,wire)
    return Event(0x201,kind=0x106,payload=bytes((0x83,3))+token+b'\0')
