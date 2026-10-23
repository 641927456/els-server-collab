"""Current3A3 full world-set for known actors in one loaded room generation.

Only committed persistence is read. Original member fields and native effects,
icons and time remain unchanged. No inventory ACK or economic request is relayed.
"""
from els_server.domain import elixir_flow as flow
from els_server.storage import world_elixirs as store
from els_server.domain.friends_spawns import _generation

def _ready(s):
    return (flow.enabled(s)and s.phase=='dungeon_active'and s.dungeon_substage_synced
        and not s.dungeon_return_pending and not s.coop_error and not s.social_overflow
        and s.application.registry.enabled(s.identity['id']))

def _relay(s):
    app=getattr(s,'application',None)
    if app is None:return 0
    dispatcher=app.world.dungeons;room=dispatcher.room(s)
    if (room is None or room.phase not in('active','part_end','clear')or not _ready(s)
        or room.party.get('run')is not room or tuple(room.party['members'])!=room.members
        or room.party['leader']is not room.leader or s not in room.members):
        s._world_elixir_peer_sent={};return 0
    own=getattr(s,'_world_elixir_sent',None)
    # Wait for the existing self path to commit its current scene snapshot.
    if not own or own[0]!=flow.context(s):return 0
    generation=_generation(room,s)
    if s.dungeon_id!=room.identity:return 0
    old=getattr(s,'_world_elixir_peer_sent',{});current={};targets=[]
    for peer in room.members:
        if (peer is s or dispatcher.room(peer)is not room or not _ready(peer)
            or peer.dungeon_id!=room.identity or _generation(room,peer)!=generation):continue
        key=(peer,peer.shop_session_id,peer.account.uid)
        cursor=(room,generation,own)
        if old.get(key)==cursor:current[key]=cursor
        else:targets.append((peer,key))
    s._world_elixir_peer_sent=current
    if not targets:return 0
    # Source actor owns both exact member profiles. A recipient's base/HP is
    # never substituted. This read validates owner/lifecycle and existing receipt.
    out=store.notice(s.account.store.path,s.account.uid,s.account.account_id,flow.prepare(s))
    if not out['events']:return 0
    actual=flow.signature(s,out['state']);cursor=(room,generation,actual)
    sent=0
    for peer,key in targets:
        # A held Town connection scheduled by another roster must not receive
        # a new room grant merely because its old in-memory lease still exists.
        try:store.snapshot(peer.account.store.path,peer.account.uid,peer.account.account_id)
        except ValueError:continue
        dispatcher.send(peer,out['events']);current[key]=cursor;sent+=1
    return sent

def relay(s):
    # This post-commit delivery exit cannot discard the original response or
    # repeat an economic operation on a temporary read/queue/encoder failure.
    try:return _relay(s)
    except Exception as exc:
        s._world_elixir_peer_error=type(exc).__name__
        return 0
