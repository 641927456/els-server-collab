"""Owned LuCiel style and bounded town/solo active state."""
from els_server.protocol.luciel_messages import acknowledgement,notification,preference,request,active_notification,active_preference,active_request

def enabled(s):
    return s.item_test and s.client_build=='dx11_260923' and s.role=='game' and s.account.characters is not None and s.account.store is not None

def peers(s):
    app=getattr(s,'application',None)
    if app is None:return None,()
    if getattr(s,'released',False) or app.playing.get(s.identity['id']) is not s:raise ValueError('LuCiel obsolete game connection')
    world=app.world
    room=world.room(s) if s.phase=='town_ready' else world.dungeons.transport_room(s)
    members=room if s.phase=='town_ready' else room.members if room is not None else ()
    if s.phase=='town_ready':
        own=room.get(s)
        if (world.members.get(s)!=(1,s.active_map) or own is None or own[0]['uid']!=s.account.uid):
            raise ValueError('LuCiel current town actor mismatch')
    targets=[]
    for other in members:
        if (other is s or other.released or other.role!='game' or other.phase!=s.phase
            or app.playing.get(other.identity['id']) is not other):continue
        if s.phase=='town_ready':
            if world.members.get(other)!=world.members.get(s) or room[other][0]['uid']!=other.account.uid:continue
        elif world.dungeons.transport_room(other) is not room:continue
        targets.append(other)
    return world,tuple(targets)

def style_context(s):
    """Snapshot the existing709 contexts, including legacy no-Application use."""
    world,targets=peers(s);app=getattr(s,'application',None)
    refs=[app,world,s.account,s.account.store,s.account.characters,getattr(s,'identity',None)]
    values=[s.account.uid,s.account.account_id,str(s.account.store.path),s.shop_session_id,
            s.role,s.phase,s.client_build,s.item_test,getattr(s,'released',False),
            getattr(s,'identity',{}).get('id')]
    room=None;entry=None
    if world is not None:
        if s.identity['id']!=s.account.account_id:raise ValueError('LuCiel style account lease')
        room=world.room(s) if s.phase=='town_ready' else world.dungeons.transport_room(s)
        refs.extend((app.playing,world.members,room))
        values.append((s.active_map,world.members.get(s)))
        if s.phase=='town_ready':
            entry=room[s];refs.extend((entry,entry[0],entry[1],entry[2]))
            values.append(repr(entry))
        elif room is not None:
            refs.extend((room.members,room.party))
            values.append((room.identity,room.seed,room.phase,repr(room.progress)))
    run=getattr(s,'dungeon_run',None)
    if s.phase=='dungeon_active':
        refs.append(run)
        values.append((getattr(s,'dungeon_id',None),getattr(s,'reward_run_id',None),
            getattr(s,'dungeon_substage_synced',None),getattr(s,'gate_stage',None),
            getattr(s,'gate_stage_loading',None),repr(vars(run)) if run is not None else None))
    for other in targets:
        mailbox=other.mailbox
        from els_server.domain.friends_world import Mailbox
        if type(mailbox) is not Mailbox:raise ValueError('LuCiel style mailbox type')
        refs.extend((other,other.account,other.identity,mailbox,mailbox.messages,mailbox.moves))
        values.append((other.account.uid,other.account.account_id,other.shop_session_id,
            other.identity['id'],other.phase,other.role,other.client_build,other.released,
            other.social_overflow,world.members.get(other),mailbox.bytes,
            tuple((id(e),repr(vars(e))) for e in mailbox.messages),
            tuple((key,id(e),repr(vars(e))) for key,e in mailbox.moves.items())))
        if s.phase=='town_ready':
            peer_entry=room[other];refs.extend((peer_entry,peer_entry[0],peer_entry[1],peer_entry[2]))
            values.append(repr(peer_entry))
    return dict(refs=tuple(refs),values=tuple(values),world=world,room=room,entry=entry,targets=targets)

def validate_style_context(s,captured):
    current=style_context(s)
    if (captured['values']!=current['values'] or len(captured['refs'])!=len(current['refs'])
        or any(a is not b for a,b in zip(captured['refs'],current['refs']))):raise ValueError('LuCiel style context changed')

def prepare_style(s,captured,reply):
    from collections import deque
    from els_server.domain.friends_world import Mailbox
    from els_server.protocol.protocol_codec import encode_event
    mailboxes=[];own=None;marker=None;room=captured['room']
    for event in reply:encode_event(event)
    if captured['entry'] is not None:
        entry=captured['entry'];character={**entry[0],'luciel_style':reply[-1].payload[-1]}
        own=(character,entry[1],entry[2]);marker=(room,character,actor_generation(s,room,entry))
    for other in captured['targets']:
        encode_event(reply[-1])
        original=other.mailbox
        clone=Mailbox();clone.messages=deque(original.messages);clone.moves=dict(original.moves);clone.bytes=original.bytes
        if clone.bytes!=sum(len(e.payload) for e in clone.messages)+sum(len(e.payload) for e in clone.moves.values()):raise ValueError('LuCiel malformed style mailbox')
        clone.append(reply[-1]);mailboxes.append((other,clone))
    validate_style_context(s,captured)
    return room,own,marker,tuple(mailboxes)

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x709:return None
    if not enabled(s):return [acknowledgement()]
    try:
        request(event.payload)
        if (s.phase not in ('town_ready','dungeon_active') or type(sequence) is not int or not 1<=sequence<2**32
            or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
            or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('LuCiel session envelope')
        captured=style_context(s);publication=[]
        from els_server.storage.luciel_state import perform
        uid=s.account.uid
        reply=perform(s.account.store.path,uid,event.payload,account_id=s.account.account_id,session_id=s.shop_session_id,sequence=sequence,
            prepare=lambda result:publication.append(prepare_style(s,captured,result)),
            validate=lambda:validate_style_context(s,captured))
    except ValueError:return [acknowledgement()]
    room,own,marker,mailboxes=publication[0]
    if own is not None:room[s]=own;s.luciel_active_actor_marker=marker
    for other,mailbox in mailboxes:other.mailbox=mailbox
    return reply

def restore(s,event,replies):
    if not enabled(s) or s.phase!='town_ready' or event.kind!=0x227 or event.event_id!=0x202:return []
    if not any(e.kind==0x228 and e.payload==bytes(4) for e in replies):return []
    character=s.account.character()
    if character['unit_type']!=10:return []
    value=preference(character)
    messages=[notification(character['uid'],value)] if value else []
    app=getattr(s,'application',None)
    if app is not None:
        if (getattr(s,'released',False) or app.playing.get(s.identity['id']) is not s
            or 0x227 not in s.completed or character['uid']!=s.account.uid):return []
    messages.insert(0,active_notification(character['uid'],active_preference(character)))
    from els_server.protocol.protocol_codec import encode_event
    for message in messages:encode_event(message)
    s.luciel_peer_sync=None
    return messages

def periodic(s):
    """Reconcile peers after22A, including bounded asynchronous actor creation.

    A newly received22A can finish creating a native actor after the first
    notices arrive. Send the latest absolute state at most once per second
    for three additional opportunities; never replay an old captured state.
    """
    if not enabled(s) or s.phase!='town_ready':
        s.luciel_peer_sync=None;s.luciel_peer_restore_retry={};return []
    try:world,targets=peers(s)
    except ValueError:
        s.luciel_peer_sync=None;s.luciel_peer_restore_retry={};return []
    if world is None or s not in world.members:
        s.luciel_peer_sync=None;s.luciel_peer_restore_retry={};return []
    room=world.room(s);context=(s.shop_session_id,s.account.uid,world.members[s],room)
    previous=getattr(s,'luciel_peer_sync',None)
    same=previous is not None and previous[0][:3]==context[:3] and previous[0][3] is room
    old=previous[1] if same else {};current={};messages=[];retry={}
    old_retry=getattr(s,'luciel_peer_restore_retry',{}) if same else {}
    import time
    now=time.monotonic()
    from els_server.protocol.protocol_codec import encode_event
    for other in targets:
        entry=room.get(other)
        if entry is None:continue
        character=other.account.character()
        if character['unit_type']!=10:continue
        uid=character['uid'];value=preference(character);active_value=active_preference(character);key=(other,uid)
        marker=(actor_generation(other,room,entry),other.shop_session_id,active_value,value)
        current[key]=marker;last=old.get(key)
        same_actor=last is not None and len(last)==4 and last[0] is marker[0] and last[1]==marker[1]
        active_changed=not same_actor or last[2]!=active_value
        style_changed=not same_actor or last[3]!=value
        if active_changed:messages.append(active_notification(uid,active_value))
        if style_changed:messages.append(notification(uid,value))
        if active_changed or style_changed:
            retry[key]=(marker,now+1.0,3)
        else:
            pending=old_retry.get(key)
            if (pending is not None and pending[0][0] is marker[0]
                and pending[0][1:]==marker[1:] and pending[2]>0):
                if now>=pending[1]:
                    messages.extend((active_notification(uid,active_value),notification(uid,value)))
                    if pending[2]>1:retry[key]=(marker,now+1.0,pending[2]-1)
                else:retry[key]=pending
    # Publishing both caches follows all throwing packet preparation. Removed,
    # foreign, released, departed and previous-generation peers are not retained.
    for event in messages:encode_event(event)
    s.luciel_peer_sync=(context,current);s.luciel_peer_restore_retry=retry
    return messages


def actor_generation(s,room,entry):
    """An active-only room replacement retains its actual actor's reference."""
    marker=getattr(s,'luciel_active_actor_marker',None)
    if marker is not None and marker[0] is room and marker[1] is entry[0]:return marker[2]
    return entry[0]

def active_context(s,kind):
    import math,uuid
    if not enabled(s):raise ValueError('LuCiel active profile')
    if kind!=0x4e2:raise ValueError('Unsupported guild-agit/housing switch')
    if s.phase=='dungeon_active' or getattr(s,'application',None) is None:
        from els_server.domain.luciel_dungeon import context
        return context(s)
    app=getattr(s,'application',None)
    if (app is None or getattr(s,'released',False) or app.playing.get(s.identity['id']) is not s
        or s.identity['id']!=s.account.account_id):raise ValueError('LuCiel active game lease')
    character=s.account.character();uid=s.account.uid
    if character['uid']!=uid or character['unit_type']!=10:raise ValueError('LuCiel active current actor')
    from els_server.game_data import client_data
    if client_data().unit(character['unit_class'])['unitType']!=10:raise ValueError('LuCiel active family')
    world=app.world;room=None;entry=None;targets=()
    refs=[app,world,s.account];values=[uid,s.account.account_id,s.shop_session_id,s.role,s.client_build,s.phase]
    if kind==0x4e2:
        if s.phase!='town_ready' or 0x227 not in s.completed:raise ValueError('LuCiel town actor not ready')
        world,targets=peers(s);room=world.room(s);entry=room.get(s)
        targets=tuple(other for other in targets if other.client_build=='dx11_260923'
                      and 0x227 in other.completed and other.identity['id']==other.account.account_id)
        if entry is None:raise ValueError('LuCiel missing town actor')
        refs.extend((room,entry[0],entry[1],entry[2]))
        values.extend((s.active_map,world.members.get(s),character['unit_class']))
        for other in targets:
            peer_entry=room[other];mailbox=other.mailbox
            refs.extend((other,other.account,mailbox,peer_entry[0],peer_entry[1],peer_entry[2]))
            values.append((other.shop_session_id,other.account.uid,other.identity['id'],other.role,other.phase,world.members.get(other),
                           mailbox.bytes,tuple(mailbox.messages),tuple(mailbox.moves.items())))
    else:raise ValueError('LuCiel unsupported active kind')
    return dict(refs=tuple(refs),values=tuple(values),world=world,room=room,entry=entry,targets=targets)

def validate_active_context(s,kind,captured):
    current=active_context(s,kind)
    if (captured['values']!=current['values'] or len(captured['refs'])!=len(current['refs'])
        or any(a is not b for a,b in zip(captured['refs'],current['refs']))):raise ValueError('LuCiel active context changed')

def prepare_active(s,kind,captured,result):
    from collections import deque
    from els_server.domain.friends_world import Mailbox
    from els_server.protocol.protocol_codec import encode_event
    room=captured['room'];mailboxes=[];own=None;marker=None
    for event in result['events']:encode_event(event)
    if room is not None:
        entry=captured['entry'];character={**entry[0],'luciel_active_unit':result['active_unit'],'luciel_style':result['style']}
        own=(character,entry[1],entry[2]);marker=(room,character,actor_generation(s,room,entry))
    notice=active_notification(s.account.uid,result['active_unit']);encode_event(notice)
    for other in captured['targets']:
        original=other.mailbox
        if type(original) is not Mailbox:raise ValueError('LuCiel peer mailbox type')
        clone=Mailbox();clone.messages=deque(original.messages);clone.moves=dict(original.moves);clone.bytes=original.bytes
        if clone.bytes!=sum(len(e.payload) for e in clone.messages)+sum(len(e.payload) for e in clone.moves.values()):raise ValueError('LuCiel malformed peer mailbox')
        clone.append(notice)
        mailboxes.append((other,clone))
    validate_active_context(s,kind,captured)
    return dict(room=room,own=own,marker=marker,mailboxes=tuple(mailboxes))

def handle_active(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x4e2,0x506):return None
    try:
        active_request(event.payload)
        if (type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
            or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('LuCiel active envelope')
        captured=active_context(s,event.kind)
        from els_server.storage.luciel_state import perform_active
        result=perform_active(s.account.store.path,s.account.uid,event.kind,event.payload,account_id=s.account.account_id,
            session_id=s.shop_session_id,sequence=sequence,
            prepare=lambda reply:prepare_active(s,event.kind,captured,reply),
            validate=lambda:validate_active_context(s,event.kind,captured))
    except ValueError:return []
    prepared=result['prepared']
    if prepared['room'] is not None:
        prepared['room'][s]=prepared['own'];s.luciel_active_actor_marker=prepared['marker']
    for other,mailbox in prepared['mailboxes']:other.mailbox=mailbox
    return result['events']
