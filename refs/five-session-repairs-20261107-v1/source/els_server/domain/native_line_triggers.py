"""Relay source-qualified activations to the existing native line-map consumer.

The original dungeon predicates and NPC AI produce the request. This relay does
not evaluate their physics, advance rooms, or perform an economic transaction.
"""
from pathlib import Path
import functools,json,struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.dungeon_equipment_loot_flow import current_lease

@functools.lru_cache(maxsize=1)
def definitions():
    data=json.loads((Path(__file__).resolve().parents[1]/'data/native_line_triggers.json').read_bytes())
    from els_server.game_data import CLIENT_SHA
    if data['format']!=1 or data['client_sha256']!=CLIENT_SHA:
        raise ValueError('Native line trigger source identity')
    return {(r['dungeon'],r['stage'],r['part'],r['trigger']):r for r in data['rules']}

def handle(s,event,request_sequence=None):
    prepared=prepare(s,event,None,request_sequence)
    if prepared is None:return None
    accepted,replies,requests=prepared
    if accepted is not None:s.dungeon_run.native_line_triggers=accepted
    if requests is not None:s.native_line_requests=requests
    return replies


def prepare(s,event,participants,request_sequence):
    run=s.dungeon_run
    if event.event_id!=0x202 or event.kind!=0x30a or run is None:
        return None
    rules=definitions()
    if run.identity not in {key[0]for key in rules}:
        return None
    from els_server.protocol.protocol_codec import encode_event
    if participants is None:participants=frozenset((s.account.uid,))
    error=(None,[Event(0x201,kind=0x30b,payload=struct.pack('>i',1836))],None)
    if (event.performers!=(0,)or event.uid!=2**64-1 or event.target_uid!=2**64-1
        or event.payload_mode!=0 or len(event.payload)!=4 or s.role!='game'
        or s.phase!='dungeon_active' or not s.dungeon_substage_synced
        or s.clear_notified or not current_lease(s)or getattr(s,'dungeon_failed',False)
        or frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=participants
        or type(request_sequence)is not int or not 1<=request_sequence<2**32):
        return error
    requests=getattr(s,'native_line_requests',{})
    identity=(run.run_id,participants,bytes(event.payload))
    previous=requests.get(request_sequence)
    if previous is not None:
        # A connection's accepted sequence keeps its original meaning across
        # curtains and B2 loads. Never deliver its old action to the new world.
        return (None,[Event(0x201,kind=0x30b,payload=bytes(4))],None)if previous[:3]==identity else error
    requests={**requests,request_sequence:(*identity,(run.stage,run.part,run.visits))}
    activation=struct.unpack('>i',event.payload)[0]
    rule=rules.get((run.identity,run.stage,run.part,activation))
    if rule is None:
        contact=rules.get((run.identity,run.stage,-1,activation))
        if contact is not None and run.part in contact['contact_parts']:rule=contact
    if rule is None:
        accepted=set(getattr(run,'native_line_triggers',()))
        late=any(stage==run.stage and visits==run.visits and value==activation
            and rules[run.identity,stage,part,value]['source_sha256']==run.graph['source_sha256']
            for stage,part,visits,value in accepted)
        if late:
            replies=[Event(0x201,kind=0x30b,payload=bytes(4))]
            for message in replies:encode_event(message)
            return accepted,replies,requests
        return error
    if run.graph['source_sha256']!=rule['source_sha256']:
        return error
    templates=rule.get('npc_templates',())
    if 'npc_template'in rule:templates=(rule['npc_template'],)
    sources=rule.get('npc_sources',())
    present=any(n['template']in templates for n in run.current['npcs'])
    if sources:
        # Original controllers can keep requesting actions after their source
        # sub-part ends. B2 owns the whole stage roster; the next B2 replaces it.
        present=present or any(not n.get('dynamic')and n['template']==source['template']
            and n.get('source_index')==source['source_index']
            for source in sources for n in run.parts[source['part']]['npcs'])
    if (templates or sources)and not present:
        return error
    accepted=set(getattr(run,'native_line_triggers',()))
    # A contact shared by adjacent parts is one original world action.
    key=(run.stage,rule['part'],run.visits,activation)
    reply=[Event(0x201,kind=0x30b,payload=bytes(4))]
    # A looping native action can be requested again after the native consumer
    # retires it. The consumer itself ignores an activation that is still active.
    if rule['native_loop'] or rule.get('native_repeat',False) or key not in accepted:
        reply.append(Event(0x201,kind=0x30c,payload=struct.pack('>i',activation)))
        accepted.add(key)
    for message in reply:encode_event(message)
    return accepted,reply,requests


def shared(dispatcher,room,s,event,request_sequence=None):
    from els_server.domain.friends_spawns import _checked_static_generation
    from els_server.domain.party_commands import _prepared_boxes
    error=[Event(0x201,kind=0x30b,payload=struct.pack('>i',1836))]
    if s not in room.members or room.phase not in ('active','part_end'):return error
    try:_checked_static_generation(dispatcher,room)
    except ValueError:return error
    if any(m.clear_notified or getattr(m,'dungeon_failed',False) for m in room.members):return error
    participants=frozenset(m.account.uid for m in room.members)
    prepared=prepare(s,event,participants,request_sequence)
    if prepared is None:return None
    accepted,response,requests=prepared
    if accepted is None:return response
    previous=set(getattr(s.dungeon_run,'native_line_triggers',()))
    if any(set(getattr(m.dungeon_run,'native_line_triggers',()))!=previous for m in room.members):return error
    notices=[e for e in response if e.kind==0x30c]
    boxes=_prepared_boxes([(m,notices) for m in room.members if m is not s],response)
    for member in room.members:member.dungeon_run.native_line_triggers=set(accepted)
    s.native_line_requests=requests
    for member,box in boxes.items():member.mailbox=box
    return response
