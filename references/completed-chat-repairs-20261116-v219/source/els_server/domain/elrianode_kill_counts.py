"""Project accepted Elrianode City kills into the original 6E6 UI consumer."""
from dataclasses import replace
import struct

from els_server.protocol.protocol_codec import Event, encode_event

GRAPH_SHA256 = '42dd2c9af39c602c9967c0ce9e73247886029e994dd6ceb0966b2ee12fd3e9b1'
# The three original ELIANODAREA_SUMMON scripts' ten hostile types each.
# Summoners, dialogue actors, player summons and the stage-one boss are absent.
TEMPLATES = frozenset((*range(2901, 2907), *range(2910, 2922),
                       *range(2931, 2940), *range(2945, 2948)))


def prepare(session, npc, death, expired, notice):
    run = session.dungeon_run
    if (run.identity != 34010 or run.stage != 0 or expired
            or npc['template'] not in TEMPLATES or not npc['active']
            or npc.get('ally') or npc.get('team', 1) == 0
            or death['killer'] not in session.dungeon_participants):
        return notice, None
    if run.graph['source_sha256'] != GRAPH_SHA256:
        raise ValueError('Elrianode kill counter original graph changed')
    counts = dict(getattr(run, 'elrianode_kills', {}))
    counts[death['killer']] = counts.get(death['killer'], 0) + 1
    # C25B90/6E6 reads result, a UID->i32 cumulative map, and an i32 total.
    # It replaces DungeonGame+1720 and increases +1730. 104A360 owns 20/90.
    payload = struct.pack('>iI', 0, len(counts))
    payload += b''.join(struct.pack('>Qi', uid, count) for uid, count in sorted(counts.items()))
    counter = Event(0x201, kind=0x6e6, payload=payload + struct.pack('>i', sum(counts.values())))
    # AF+4 is the NPC template, consumed by 1AAF540 to select region 5/7/9.
    notice = replace(notice, payload=notice.payload[:4] + struct.pack('>i', npc['template']) + notice.payload[8:])
    encode_event(notice)
    encode_event(counter)
    return notice, (counts, counter)
