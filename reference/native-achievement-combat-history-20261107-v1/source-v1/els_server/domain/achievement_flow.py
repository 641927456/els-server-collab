"""Ordinary achievement requests use the authenticated actor and one SQL writer."""
from contextlib import closing
from pathlib import Path
import sqlite3,time
from els_server.domain.friend_flow import capture
from els_server.domain.pvp_registration import _envelope
from els_server.domain.achievement_catalog import progress_projection,points
from els_server.domain.local_session import SessionOrderError
from els_server.protocol import achievement_messages as wire
from els_server.protocol.local_messages import i32
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import achievements as state
from els_server.storage.achievement_profiles import reconcile as reconcile_profiles
from els_server.storage.item_actor import require_active_character


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in wire.REQUESTS|{0x6c3,0x6c5}:return None
    guard=capture(s)
    if (not _envelope(event)or type(sequence)is not int or not 1<=sequence<2**32
            or s.phase in('closing','channels_ready')or s.account.store.uid!=s.account.uid):
        raise SessionOrderError('Achievement actor or request envelope changed')
    if event.kind in(0x6c3,0x6c5):
        return [wire.message(event.kind+1,i32(1367))]
    try:parsed=wire.request(event.kind,event.payload)
    except ValueError as error:raise SessionOrderError(str(error))from error
    account,owner=s.account.account_id,s.account.uid
    operation=f'{s.shop_session_id}:achievement:{owner}:{sequence}'
    with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,owner)
        completed=reconcile_profiles(db,account,owner,int(time.time()))['completed']if event.kind==0x6be else []
        code=0;identity=parsed.get('achievement')
        try:
            if event.kind==0x6c1:state.toggle_display(db,account,owner,identity,operation)
            elif event.kind==0x6c9:state.claim(db,account,owner,identity,int(time.time()))
        except state.AchievementError as error:code=error.code
        current=state.snapshot(db,account,owner)
        if event.kind==0x6be:
            answer=[wire.summary(points(current['completed']),current['watched'],False),
                    wire.initialization([],progress_projection(current),current['completed'],current['watched'])]
        elif event.kind==0x6c1:answer=[wire.watch_ack(code,current['watched'])]
        else:
            row=next((row for row in current['completed']if row['id']==identity),dict(completed_at='',received=False))
            answer=[wire.reward_ack(code,identity,row['completed_at'],row['received'])]
        for message in answer:encode_event(message)
        guard(db);require_active_character(db,owner)
    if completed or event.kind==0x6c1 and code==0:_appearance_changed(s)
    return answer


def _appearance_changed(s):
    if s.phase=='town_ready':
        with s.application.world_lock:s.application.world.appearance_changed(s)
    elif s.phase=='guild_agit_ready':
        from els_server.domain.guild_agit_flow import bank_capture,_peers,_row
        from els_server.domain.party_commands import _prepared_boxes
        from els_server.protocol import guild_agit_messages as guild_wire
        with s.application.world_lock:
            _,guard=bank_capture(s)
            with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
                db.execute('BEGIN');guard(db)
                peers=_peers(s,s.guild_agit['guild'])
                row=_row(s)
                notices=[guild_wire.removed(s.account.uid),guild_wire.added(row)]
                if row[0]['unit_type']==11:
                    from els_server.domain.guild_rose import notification as rose_notice
                    notices.append(rose_notice(s.account.uid,row[0]['guild_rose_weapon']))
                boxes=_prepared_boxes([(peer,notices)for peer,_,_ in peers],[])
                for _,_,peer_guard in peers:peer_guard(db)
                guard(db)
            for peer,box in boxes.items():peer.mailbox=box


def synchronize(s,event,response):
    cold=any(row.event_id==0x201 and row.kind==0x2f for row in response)
    arrival=event is not None and event.event_id==0x202 and event.kind==0x227 and s.phase=='town_ready'
    kinds={row.kind for row in response if row.event_id==0x201};sources=set()
    if kinds&{0x4c3,0x4c4,0xd9}:sources.update((6,15))
    if kinds&{0x29f,0x59f,0xd9}:sources.update((67,68))
    if kinds&{0x2e9,0x433}:sources.update((37,38))
    if kinds&{0x552,0x105,0x373}:sources.add(39)
    if 0xc23 in kinds:sources.add(42)
    if 0x18b in kinds:sources.add(27)
    if 0x1d0 in kinds:sources.add(28)
    if 0x3ff in kinds:sources.add(18)
    if 0x424 in kinds:sources.add(19)
    if 0xc1 in kinds:sources.add(2)
    if 0xc2 in kinds:sources.update((4,5))
    if 0x291 in kinds:sources.add(23)
    if 0x27e in kinds:sources.add(26)
    if 0x804 in kinds:sources.add(56)
    if kinds&{0x241,0xf5,0x802,0x804,0xabd}:sources.add(25)
    if 0x719 in kinds:sources.add(16)
    if 0x612 in kinds:sources.add(43)
    if 0x614 in kinds:sources.add(44)
    if 0x600 in kinds:sources.add(32)
    if 0x1c5 in kinds:sources.add(45)
    if 0x706 in kinds:sources.add(51)
    if 0x708 in kinds:sources.add(52)
    if 0x9b4 in kinds:sources.add(53)
    if 0x6e8 in kinds:sources.add(60)
    if 0x115 in kinds:sources.add(35)
    if 0x161 in kinds:sources.add(36)
    if 0x8b8 in kinds:sources.update((61,62))
    if 0x8c4 in kinds:sources.add(63)
    # Original guild refusal has no ACK. Only its committed6C8 action journal
    # can increase the count; replay or a refusal without an invitation cannot.
    if event is not None and event.event_id==0x202 and event.kind==0x6c8:sources.add(24)
    if not cold and not arrival and not(sources and s.role=='game'and s.phase in('town_ready','guild_agit_ready','dungeon_active','wedding_hall','pvp_result')):return response
    guard=capture(s)
    with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
        options={}if cold or arrival else dict(condition_types=sources)
        updated=reconcile_profiles(db,s.account.account_id,s.account.uid,int(time.time()),**options)
        if not cold and not arrival and not updated['completed']:
            guard(db);return response
        current=state.snapshot(db,s.account.account_id,s.account.uid)
        # Preserve the pre-existing full-user DTO's false state flag. Its
        # separate consumer remains a native-contract audit item; this does
        # not assign privilege, progress, items or a claimed-reward marker.
        scores=points(current['completed'])
        if cold or arrival:message=wire.summary(scores,current['watched'],False)
        else:
            fresh=set(updated['completed'])
            message=wire.completion([row for row in current['completed']if row['id']in fresh],scores,current['watched'],False)
        encode_event(message);guard(db)
    if updated['completed']:_appearance_changed(s)
    return [*response,message]
