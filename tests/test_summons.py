"""Native captured sentry request, validation, duplicate and scene boundaries."""
import json,struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.summons import sentry_spawn,LAYOUTS,_decode
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event
fixture=json.loads((ROOT/'analysis/skills-clear-20261015/sentry-request.json').read_text())
body=bytes.fromhex(fixture['payload'])
positions={r['offset']:r['position'] for r in fixture['segments']}
notice=sentry_spawn(body,1002,16)
assert notice.kind==0x2d0 and notice.payload[-24:]==bytes(24)
# Normalize the emitted identity back to the request sentinel for the decoder.
from els_server.domain.dungeon_npcs import MODE0_FIELDS
position=4
for off,size,xor,kind in MODE0_FIELDS:
    if off==0:break
    position+=size
assert int.from_bytes(notice.payload[position:position+4],'big')^0x8d0dbb13==16
# A second independent live request uses mode 2 and originally reproduced the
# blank error. It must canonicalize to the same DTO shape, without padding.
from els_server.protocol.protocol_codec import decode_event
for row in json.loads((ROOT/'analysis/skills-clear-20261015/sentry-rejected-request.json').read_text()):
    captured=decode_event(bytes.fromhex(row['wire_hex'])).payload
    assert len(sentry_spawn(captured,1002,16).payload)==144
# Check each recovered permutation's inverse, including the native padding
# string, against the independent captured DTO rather than a default zero DTO.
dto=bytes.fromhex(fixture['dto'])
for fields in LAYOUTS.values():
    encoded=[struct.pack('>I',1)]
    for off,size,xor,kind in fields:
        if kind=='empty':encoded.append(struct.pack('>I',3)+b'abc' if off is None else bytes(4))
        elif size==12:encoded.append(b''.join(dto[off+i:off+i+4][::-1] for i in (0,4,8)))
        else:encoded.append((int.from_bytes(dto[off:off+size],'little')^xor).to_bytes(size,'big'))
    encoded=b''.join(encoded)
    assert bytes(_decode(encoded,1002,fields))==dto
    assert sentry_spawn(encoded,1002,16)==notice
for n in range(len(body)):
    try:sentry_spawn(body[:n],1002,16)
    except ValueError:pass
    else:raise AssertionError('Truncated request accepted')
bad=[]
for off,value in [(4,struct.pack('>I',385^0xaa1cb53c)),(0x6d,struct.pack('>Q',1001^0x39cb1d467db8934e)),(9,struct.pack('>f',float('nan')))]:
    b=bytearray(body);b[positions[off]:positions[off]+len(value)]=value;bad.append(bytes(b))
bad += [body+b'\0',struct.pack('>I',2)+body[4:]]
for b in bad:
    try:sentry_spawn(b,1002,16)
    except ValueError:pass
    else:raise AssertionError('Invalid summon accepted')
with tempfile.TemporaryDirectory() as tmp:
    root=LocalAccount(LocalState(Path(tmp)/'save.db'));root.enable_characters()
    eve=root.characters.create('EveTest',5,'create');assert eve['uid']==1002
    s=LocalSession(root.for_character(1002),enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True)
    s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True
    request=Event(0x202,kind=0x2ce,payload=body)
    response=s.handle(request,50);assert [r.kind for r in response]==[0x2cf,0x2d0]
    assert s.handle(request,50)==response[:1] and s.summon_next_key==17
    assert s.handle(Event(0x202,kind=0x2ce,payload=body+b'\0'),50)[0].payload==struct.pack('>i',-1)
    # Native expiry capture, with its outgoing index repaired to the actor UID.
    from els_server.domain.dungeon_lifecycle import death_report
    captured_deaths=json.loads((ROOT/'analysis/skills-clear-20261015/sentry-death-reports.json').read_text())
    expired=next(decode_event(bytes.fromhex(r['wire_hex'])) for r in captured_deaths
                 if death_report(decode_event(bytes.fromhex(r['wire_hex'])).payload)['flag']==255)
    def expiry(key):
        return Event(0x202,performers=(0,),kind=0xad,payload=struct.pack('>i',key)+expired.payload[4:])
    # Unknown keys and ordinary enemy IDs cannot use the expiry exception.
    for key in (0,8,17,79):assert s.handle(expiry(key))==[]
    assert s.summon_keys=={16} and not s.defeated_npcs
    assert [e.kind for e in s.handle(expiry(16))]==[0xae,0xaf]
    assert [e.kind for e in s.handle(expiry(16))]==[0xae]
    assert not s.defeated_npcs and not s.part_end_notified and not s.world_drops
    # Conflicting body/owner, absent performers and expired scene fail closed.
    for off,raw in [(5,struct.pack('>Q',1002)),(13,struct.pack('>Q',1002)),(45,b'\0'),(58,struct.pack('>Q',999))]:
        corrupt=bytearray(expiry(16).payload);corrupt[off:off+len(raw)]=raw
        assert s.handle(Event(0x202,performers=(0,),kind=0xad,payload=bytes(corrupt)))==[]
    assert s.handle(Event(0x202,kind=0xad,payload=expiry(16).payload))==[]
    # Native instance identity is independent of the 80 concurrent slots.
    # A long encounter can retire and summon again without reusing old IDs.
    for sequence in range(1000,1105):
        key=s.summon_next_key
        assert [e.kind for e in s.handle(request,sequence)]==[0x2cf,0x2d0]
        assert [e.kind for e in s.handle(expiry(key))]==[0xae,0xaf]
    assert max(s.summon_keys)>80 and len(s.summon_keys)==106
    # Actual stage-one wire: the killed native UID8 was incorrectly sent as0
    # because its vector slot had shifted to9. Replaying just the verified
    # identity correction must release the real gate only after all8 enemies.
    s.gate_stage=1;s.defeated_npcs={}
    from els_server.domain.dungeon_population import population
    stage=population(1)
    enemy=next(decode_event(bytes.fromhex(r['wire_hex'])) for r in captured_deaths
               if r['timestamp']==1792006138088)
    assert death_report(enemy.payload)['index']==0
    assert s.handle(enemy)==[]
    for key in range(1,9):
        assert [e.kind for e in s.handle(Event(0x202,performers=(0,),kind=0xad,
            payload=struct.pack('>i',key)+enemy.payload[4:]))]==[0xae,0xaf]
    assert set(s.defeated_npcs)==set(range(1,9)) and not s.part_end_notified
    gate=bytearray(enemy.payload);struct.pack_into('>i',gate,0,9);struct.pack_into('>f',gate,46,stage['npcs'][9]['hp'])
    assert [e.kind for e in s.handle(Event(0x202,performers=(0,),kind=0xad,payload=bytes(gate)))]==[0xae,0xaf,0xba]
    s.part_end_notified=False;s.defeated_npcs={}
    s.clear_notified=True;assert s.handle(request,51)[0].payload==struct.pack('>i',-1)
    s.clear_notified=False;s.phase='town_ready';assert s.handle(request,51)[0].payload==struct.pack('>i',-1)
    assert s.defeated_npcs=={} and not s.part_end_notified
print('PASS: captured sentry, owner/template/position validation, all truncations, retry, scene and clear isolation.')
