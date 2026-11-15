"""Steel Wall native cinematic votes: 1AE7920 -> 4B5 -> BD9320 -> 1AE7BE0."""
import struct
from els_server.protocol.protocol_codec import Event

GRAPH_SHA='1e010c5a23db8aaf3acc9bbbb7a7db93d705c7e3fc995cbc817ce01842711877'
# Original cinematic controllers, not damageable Bosses or ordinary actors.
CONTROLLERS={0:{8930:None},1:{8931:8904},2:{8932:None,8933:8905}}

def handle(s,event,sequence=None):
    if event.event_id!=0x202 or event.kind!=0x4b5:return None
    run=s.dungeon_run
    if (s.client_build!='dx11_260923' or s.role!='game' or run is None
            or run.identity!=35110 or run.graph['source_sha256']!=GRAPH_SHA
            or s.phase!='dungeon_active' or not s.dungeon_substage_synced
            or s.clear_notified or s.part_end_notified or event.payload_mode!=0):return []
    if event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=2**64-1:return []
    dispatcher=s.application.world.dungeons;room=dispatcher.room(s)
    if room is None or room.phase!='active' or room.aborted or s not in room.members:return []
    from els_server.domain.friends_spawns import _checked_static_generation
    try:_checked_static_generation(dispatcher,room)
    except ValueError:return []
    allowed=CONTROLLERS.get(run.stage,{})
    body=event.payload
    if len(body)<4:return []
    count=struct.unpack_from('>I',body)[0]
    if not 1<=count<=len(allowed) or len(body)!=4+4*count:return []
    keys=struct.unpack_from('>'+count*'i',body,4)
    if len(set(keys))!=count:return []
    members=room.members
    if any(m.clear_notified or m.part_end_notified or m.dungeon_failed for m in members):return []
    npcs={n['key']:n for n in run.current['npcs']}
    for key in keys:
        npc=npcs.get(key)
        if npc is None or npc['template']not in allowed or key in run.defeated:return []
        prerequisite=allowed[npc['template']]
        if prerequisite is not None and not any(n['template']==prerequisite and n['key']in run.defeated for n in npcs.values()):return []
    identity=(run.stage,run.part,run.visits,tuple(sorted(keys)))
    votes=room.cinematic_skip_votes.get(identity,set())
    if votes is None or s in votes:return []
    votes=votes|{s}
    # Official dungeon rule: up to four participants agree; a two-person room needs both.
    if len(votes)<min(4,len(members)):
        room.cinematic_skip_votes[identity]=votes
        return []
    notice=Event(0x201,kind=0x4b5,payload=body)
    from els_server.domain.party_commands import _prepared_boxes
    boxes=_prepared_boxes([(member,[notice])for member in members if member is not s],[notice])
    room.cinematic_skip_votes[identity]=None
    for member,mailbox in boxes.items():member.mailbox=mailbox
    return [notice]
