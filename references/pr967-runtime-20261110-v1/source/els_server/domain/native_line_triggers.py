"""Relay verified unconditional line triggers to the original native consumer."""
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

def handle(s,event):
    run=s.dungeon_run
    if event.event_id!=0x202 or event.kind!=0x30a or run is None:
        return None
    rules=definitions()
    if run.identity not in {key[0]for key in rules}:
        return None
    error=[Event(0x201,kind=0x30b,payload=struct.pack('>i',-1))]
    if (event.performers!=(0,)or event.uid!=2**64-1 or event.target_uid!=2**64-1
        or event.payload_mode!=0 or len(event.payload)!=4 or s.role!='game'
        or s.phase!='dungeon_active' or not s.dungeon_substage_synced
        or s.part_end_notified or s.clear_notified or not current_lease(s)
        or getattr(s,'dungeon_failed',False)
        or frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=frozenset((s.account.uid,))):
        return error
    trigger=struct.unpack('>i',event.payload)[0]
    rule=rules.get((run.identity,run.stage,run.part,trigger))
    if rule is None or run.graph['source_sha256']!=rule['source_sha256']:
        return error
    accepted=getattr(run,'native_line_triggers',None)
    if accepted is None:
        accepted=run.native_line_triggers=set()
    key=(run.stage,run.part,run.visits,trigger)
    reply=[Event(0x201,kind=0x30b,payload=bytes(4))]
    if key not in accepted:
        reply.append(Event(0x201,kind=0x30c,payload=struct.pack('>i',trigger)))
        accepted.add(key)
    return reply
