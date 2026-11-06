"""Pinned DX11 player summon request (2CE), acknowledgement (2CF), spawn (2D0).

Native witnesses: 200ACF0 -> 113DAF0 -> 1AA9D90 -> 1B21990;
1AADA00 reads the ACK; C50040/1AADAA0 decode and create the spawn.
Twenty native field permutations share one DTO. Decode strictly and emit the
independently native-tested mode 0. The opaque padding string is not forwarded.
"""
import math
import struct
import json
from pathlib import Path
from els_server.domain.dungeon_npcs import encode_npc
from els_server.protocol.protocol_codec import Event
from els_server.domain.summon_rules import player_summon_templates, PLAYER_SUMMON_TEMPLATES
LAYOUTS=json.loads((Path(__file__).resolve().parents[1]/'data/npc_wire_layouts.json').read_text())['layouts']


def _decode(payload, uid, fields, templates=(384,), *, extensions=None):
    if len(payload) < 4 or struct.unpack_from('>I', payload)[0] != 1:
        raise ValueError('Expected one sentry')
    dto = bytearray(0xa4)
    position = 4
    extra = {}
    for offset, size, xor, kind in fields:
        if position + size > len(payload):
            raise ValueError('Truncated summon')
        raw = payload[position:position + size]
        position += size
        if kind == 'empty':
            count = int.from_bytes(raw, 'big')
            if offset is None:
                if count > 64 or position + count > len(payload):
                    raise ValueError('Summon byte-vector bound')
                position += count
            elif count:
                # Original DC6190/DAEC70 are i32 vectors; DB1910 is an
                # ordered i32/i32 map. Skill entities carry native parameters
                # here; the old Sentry-only empty check rejected those casts.
                width = 8 if offset == 0x94 else 4
                end = position + count * width
                if extensions is None or offset not in (0x19, 0x31, 0x94) or count > 64 or end > len(payload):
                    raise ValueError('Summon parameter bound')
                if offset == 0x94:
                    keys = [struct.unpack_from('>i', payload, position + i * 8)[0] for i in range(count)]
                    if any(a >= b for a, b in zip(keys, keys[1:])):
                        raise ValueError('Summon parameter map order')
                extra[offset] = raw + payload[position:end]
                position = end
            continue
        if size == 12:
            value = b''.join(raw[i:i+4][::-1] for i in (0,4,8))
        else:
            value = (int.from_bytes(raw, 'big') ^ xor).to_bytes(size, 'little')
        dto[offset:offset+size] = value
    if position != len(payload):
        raise ValueError('Trailing summon bytes')
    key, template = struct.unpack_from('<ii', dto)
    if key != -1 or template not in templates:
        raise ValueError('Unverified summon template')
    if struct.unpack_from('<q', dto, 0x6d)[0] != uid:
        raise ValueError('Summon owner mismatch')
    if not all(math.isfinite(v) and abs(v) <= 100000 for v in struct.unpack_from('<fff', dto, 9)):
        raise ValueError('Invalid summon location')
    if extensions is not None:
        extensions.update(extra)
    return dto


def sentry_spawn(payload, uid, instance_key, templates=(384,)):
    # Instance identity is distinct from the 80 concurrent native slots.
    # Original 1AA4A40 compares actor+3D0 (including IDs above 79).
    if type(instance_key) is not int or not 16 <= instance_key < 16384:
        raise ValueError('Summon instance range')
    candidates=[]
    for fields in LAYOUTS.values():
        extra = {}
        try:candidates.append((_decode(payload,uid,fields,templates,extensions=extra), extra))
        except ValueError:continue
    if len(candidates)!=1:
        raise ValueError('Unrecognized or ambiguous sentry encoding')
    dto,extra=candidates[0]
    # Preserve the native team, facing, level, owner and skill parameters.
    # Allocate only the instance identity; never recycle enemy slots 0..15.
    struct.pack_into('<i', dto, 0, instance_key)
    # C50040: vector<NPC>, init-map, scalar, bytes, stats-map, two maps.
    return Event(0x201, kind=0x2d0, payload=struct.pack('>I',1)+encode_npc(dto,0,extensions=extra)+bytes(24))


def summon_ack(result=0):
    return Event(0x201, kind=0x2cf, payload=struct.pack('>i', 1 if result == -1 else result))


def valid_sentry_death(data, uid):
    """Audited native expiry, distinct from player-attributed enemy deaths."""
    return (data['flag']==255 and data['status']==1
            and data['source']==data['killer']==0xffffffffffffffff
            and data['last_uid']==data['extra_uid']==0
            and not data['contribution'] and not data['counters']
            and data['readiness']=={uid:0})


def valid_player_summon_death(data, uid, actors):
    """Owner-authenticated expiry or the existing native combat-death format.

    Callers first bind the reported index to this owner's spawned actor. Combat
    attribution is bounded to this scene, then discarded by the empty-reward AF.
    It never reaches enemy kills, player deaths, quests or settlement.
    """
    if data['flag'] == 255:
        return valid_sentry_death(data, uid)
    identities = {0, 2**64-1, uid, *actors}
    hp = struct.unpack('>f', struct.pack('>I', data['hp_bits']))[0]
    return (data['flag'] in (0, 1) and data['status'] in (0, 1)
            and math.isfinite(hp) and hp > 0
            and all(data[k] in identities for k in ('source','killer','last_uid','extra_uid'))
            and all(set(data[k]) <= identities for k in ('contribution','readiness','counters')))
