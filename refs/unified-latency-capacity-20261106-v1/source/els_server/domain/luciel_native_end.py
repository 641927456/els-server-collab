"""Save native end-report active state before detaching the admitted actor.

This context accepts terminal dungeon states without relaxing live4E2/38E
guards. It never turns client statistics into reward or attribute writes.
"""
import math,uuid


def context(s):
    from els_server.domain.luciel_dungeon import actor,canonical
    from els_server.domain.dungeon_routes import DungeonRun
    app,refs,values=actor(s)
    if (s.phase!='dungeon_active' or not s.enter_dungeon or not s.reward_test or not s.population_test
        or s.dungeon_return_pending or s.dungeon_end_payload is not None):raise ValueError('LuCiel end actor phase')
    if (getattr(s,'solo_challenge_party',None) is not None or getattr(s,'active_challenge',None) is not None
        or getattr(s,'challenge_deadline',None) is not None):raise ValueError('LuCiel unsupported end context')
    run=s.dungeon_run
    if run is None:
        if s.dungeon_id!=30000 or type(s.gate_stage) is not int or not 0<=s.gate_stage<=2:raise ValueError('LuCiel end base run')
    else:
        if (type(run) is not DungeonRun or run.identity!=s.dungeon_id or run.stage!=s.gate_stage
            or type(run.part) is not int or run.part not in run.parts
            or type(run.started_at) not in (int,float) or not math.isfinite(run.started_at) or run.started_at<0):raise ValueError('LuCiel end admitted run')
        canonical(run.run_id,4);refs.extend((run,run.graph,run.current));values.append(repr(vars(run)))
    world=app.world if app else None;room=world.dungeons.room(s) if world else None
    if world and (s in world.members or world.dungeons.transport_room(s) is not room):raise ValueError('LuCiel end world mismatch')
    if room is None:
        if world and s in world.party_of:raise ValueError('LuCiel missing end room')
        if getattr(s,'dungeon_participants',frozenset((s.account.uid,)))!=frozenset((s.account.uid,)):raise ValueError('LuCiel end solo participants')
        canonical(s.reward_run_id,4)
        if run is not None and run.run_id!=s.reward_run_id:raise ValueError('LuCiel end solo generation')
    else:
        from els_server.domain.friends_dungeon import Room
        if (type(room) is not Room or room.identity!=s.dungeon_id or not app.config.friends_coop_enabled
            or room.phase not in ('active','clear','part_end','substage') or not 2<=len(room.members)<=6
            or s not in room.members or world.party_of.get(s) is not room.party or room.party.get('run') is not room
            or room.party.get('challenge') or room.party.get('challenge_pending')
            or tuple(room.party.get('members',()))!=room.members or type(room.party.get('ready')) is not set):raise ValueError('LuCiel end shared room')
        canonical(room.seed,4)
        if (s.reward_run_id!=str(uuid.uuid5(uuid.UUID(room.seed),'reward:'+str(s.account.uid)))
            or run is not None and run.run_id!=room.seed
            or s.dungeon_participants!=frozenset(m.account.uid for m in room.members)):raise ValueError('LuCiel end shared generation')
        refs.extend((room,room.members,room.party,room.party['members'],room.party['ready'],world.dungeons.rooms))
        values.append((room.identity,room.seed,room.phase,room.leader,tuple(room.party['ready'])))
        for member in room.members:
            refs.extend((member,member.account,world.dungeons.room(member)))
            values.append((member.account.uid,member.released,member.clear_notified,member.coop_error,member.dungeon_participants))
    values.extend((s.dungeon_id,s.reward_run_id,s.gate_stage,s.dungeon_substage_synced,s.gate_stage_loading,
                   s.clear_notified,s.dungeon_failed,s.part_end_notified,repr(s.reward_receipt),s.dungeon_return_pending,
                   s.enter_dungeon,s.reward_test,s.population_test))
    return dict(refs=tuple(refs),values=tuple(values),world=world,room=room)


def validate(s,captured):
    current=context(s)
    if (current['values']!=captured['values'] or len(current['refs'])!=len(captured['refs'])
        or any(a is not b for a,b in zip(current['refs'],captured['refs']))):raise ValueError('LuCiel changed end context')


def replies(s,active):
    from els_server.protocol import dungeon_messages
    from els_server.protocol.protocol_codec import encode_event
    snapshot=s.account.get_inventory_snapshot();updates=[]
    if s.clear_notified and not s.clear_items_synced:
        awarded={i['uid'] for i in (s.reward_receipt or {}).get('items',[])}
        updates=[i for i in snapshot['items'] or [] if i['uid'] in awarded]
    character={**s.account.character(),'luciel_active_unit':active}
    reply=[dungeon_messages.end_ack(),dungeon_messages.return_user_sync(s.account.get_location(),s.account.get_skills(),
        snapshot['balances'],snapshot['items'],character,inventory_updates=updates)]
    for event in reply:encode_event(event)
    return reply


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x67:return None
    from els_server.domain.luciel_state import enabled
    if not enabled(s) or s.account.character()['unit_type']!=10:return None
    from els_server.protocol.luciel_end_messages import request
    from els_server.storage.luciel_native_status import perform
    from els_server.domain.luciel_dungeon import actor
    try:
        if (type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
            or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('LuCiel end envelope')
        active=request(event.payload);actor(s)
        if s.dungeon_end_payload is not None:
            from els_server.protocol.dungeon_messages import end_ack
            return [end_ack()] if s.dungeon_return_pending and s.phase=='map_loading' and event.payload==s.dungeon_end_payload else []
        captured=context(s);reply=replies(s,active);validate(s,captured)
        result=perform(s.account.store.path,s.account.uid,event.payload,account_id=s.account.account_id,
            session_id=s.shop_session_id,epoch=s.reward_run_id,sequence=sequence,kind=0x67,
            validate=lambda:validate(s,captured),prepare=lambda result:None)
        if result['stale_or_retry']:return []
    except ValueError:return []
    # All throwing packet construction and lease checks precede the SQL commit.
    # Detach's ordinary Room mutations are the existing game exit behavior.
    if captured['room'] is not None:captured['world'].dungeons.detach(s)
    s.dungeon_end_payload=bytes(event.payload);s.phase='map_loading';s.pending_map=None
    s.dungeon_return_pending=True;s.inventory_town_sync_sent=True
    return reply
