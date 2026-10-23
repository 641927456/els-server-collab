"""Read-only current companion inputs for already admitted remote actors.

Runs on the existing serialized one-second notification path. Native consumers
own actor creation, AI, effects, attacks and timers; no self ACK is mirrored.
"""
import sqlite3,struct
from contextlib import closing
from pathlib import Path
from els_server.protocol import companion_peer_messages as wire
from els_server.protocol.protocol_codec import encode_event

def live(s,app,authority):
    if not (s.application is app and not s.released and not s.social_overflow and not s.coop_error
        and s.role=='game' and s.client_build=='dx11_260923' and s.item_test
        and s.identity['id']==s.account.account_id and app.playing.get(s.identity['id']) is s
        and s.account.characters is not None and s.account.store is not None):return False
    identity=(s.shop_session_id,s.account,s.account.uid,s.account.account_id,id(s.identity))
    saved=authority.get(s)
    if saved is None or saved[0]!=identity:
        current=s.account.character_identity()
        valid=app.registry.enabled(s.identity['id']) and current is not None and current['uid']==s.account.uid
        saved=(identity,valid);authority[s]=saved
    return saved[1]

def context(s,authority):
    app=s.application;world=app.world
    if not live(s,app,authority):return None
    if s.phase=='town_ready':
        room=world.room(s);key=world.members.get(s)
        if key!=(1,s.active_map) or s not in room or 0x227 not in s.completed:return None
        peers=[]
        for other,entry in tuple(room.items()):
            if (other is not s and live(other,app,authority) and other.phase=='town_ready' and 0x227 in other.completed
                and world.members.get(other)==key and entry[0]['uid']==other.account.uid):
                peers.append((other,entry[0]))
        return (room,s.shop_session_id,s.account.uid,key),tuple(peers)
    if s.phase!='dungeon_active':return None
    from els_server.domain.friends_dungeon import Room
    room=world.dungeons.room(s)
    if (type(room) is not Room or room.phase!='active' or not app.config.friends_coop_enabled
        or not 2<=len(room.members)<=6 or s not in room.members or room.party.get('run') is not room
        or tuple(room.party.get('members',()))!=room.members or room.party.get('challenge') or room.party.get('challenge_pending')):return None
    participants=frozenset(other.account.uid for other in room.members)
    if len(participants)!=len(room.members):return None
    for other in room.members:
        if (not live(other,app,authority) or other.phase!='dungeon_active' or not other.dungeon_substage_synced
            or other.gate_stage_loading or other.dungeon_return_pending or other.dungeon_end_payload is not None
            or other.clear_notified or other.dungeon_failed or other.part_end_notified
            or world.dungeons.room(other) is not room or world.party_of.get(other) is not room.party
            or other.gate_stage!=s.gate_stage or other.dungeon_id!=room.identity
            or other.dungeon_participants!=participants):return None
    return (room,s.shop_session_id,s.account.uid,(room.seed,s.gate_stage,getattr(s.dungeon_run,'part',None))),tuple((other,other.shop_session_id) for other in room.members if other is not s)

def projection(s):
    owner=s.account.uid
    with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('BEGIN')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'companions','companion_active'}<=tables:return None,None
        active=db.execute('SELECT pet,mount,mounted FROM companion_active WHERE owner=?',(owner,)).fetchone()
        if active is None:return None,None
        pet=None;mount=None
        if active[0]:
            from els_server.storage.companion_state import rows
            pet=next((p for p in rows(db,owner,'pet') if p['uid']==active[0]),None)
            if pet is None:raise ValueError('Current remote pet ownership')
            from els_server.storage.boosting_2026_limited_pet import require_current,ExpiredLimitedPet
            try:require_current(pet)
            except ExpiredLimitedPet:pet=None
        if active[2]:
            row=db.execute("SELECT uid,unit FROM companions WHERE uid=? AND owner=? AND kind='mount'",(active[1],owner)).fetchone()
            if row is None:raise ValueError('Current remote mount ownership')
            from els_server.domain.mount_rules import template
            template(row[1])
            if 0<row[1]<10000:mount=row
        return wire.pet(owner,pet) if pet else None,mount

def invalidate(s):
    cache=getattr(s.application,'companion_peer_read_cache',None)
    if cache is not None:
        cache[1].pop(s,None);cache[2].pop(s,None)

def receive(s,*,now=None):
    from els_server.domain.local_session import SessionOrderError
    published=getattr(s,'companion_peer_projection',None)
    try:return _receive(s,now=now)
    except SessionOrderError:raise
    except (sqlite3.Error,ValueError,OverflowError,struct.error):
        # A bad peer input cannot disconnect an unrelated receiver or discard
        # its already constructed ordinary notifications. Retry after repair.
        s.companion_peer_projection=published
        cache=getattr(s.application,'companion_peer_read_cache',None)
        if cache is not None:
            cache[1].clear();cache[2].clear()
        return []

def _receive(s,*,now=None):
    if now is None:
        import time
        now=time.monotonic()
    # Bound DB authority/identity reads as well as companion reads to one per
    # source in this existing poll epoch. In-memory leases remain checked on
    # every use; selection/account/session changes invalidate cached identity.
    epoch=int(now);cache=getattr(s.application,'companion_peer_read_cache',None)
    if cache is None or cache[0]!=epoch:
        cache=(epoch,{},{});s.application.companion_peer_read_cache=cache
    current=context(s,cache[2])
    if current is None:
        s.companion_peer_projection=None;return []
    scope,peers=current;old=getattr(s,'companion_peer_projection',None)
    same=old is not None and old[0][0] is scope[0] and old[0][1:]==scope[1:]
    previous=old[1] if same else {};saved={};messages=[]
    # N sources are read at most once during the existing one-second poll
    # epoch, even when N receivers inspect the same room. No inventory scan.
    # A successful/failing explicit companion request invalidates its source.
    for other,actor in peers:
        uid=other.account.uid;identity=(other.shop_session_id,uid,str(other.account.store.path))
        cached=cache[1].get(other)
        if cached is None or cached[0]!=identity:
            cached=(identity,projection(other));cache[1][other]=cached
        pet,mount=cached[1]
        old_peer=previous.get(other)
        same_actor=old_peer is not None and old_peer[0] is actor and old_peer[1]==(other.shop_session_id,uid)
        old_pet=old_peer[2] if same_actor else None;old_mount=old_peer[3] if same_actor else None
        if pet!=old_pet:
            messages.append(pet if pet is not None else wire.pet(uid))
        if mount!=old_mount:
            if old_mount is not None:messages.append(wire.dismount(uid,old_mount[1]))
            if mount is not None:messages.append(wire.mount(uid,*mount))
        saved[other]=(actor,(other.shop_session_id,uid),pet,mount)
    for event in messages:encode_event(event)
    # Nothing is published on SQL/read/encoding failure. Retry reads the latest
    # current state; departed peers and previous actor generations are dropped.
    s.companion_peer_projection=(scope,saved)
    return messages
