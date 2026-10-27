"""Pinned DX11 sentry request (2CE), acknowledgement (2CF), spawn (2D0).

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
LAYOUTS=json.loads((Path(__file__).resolve().parents[1]/'data/npc_wire_layouts.json').read_text())['layouts']

# Eve player summon family, pinned from the client NPC catalog. 384
# Nasod_Watch_Eve is the admitted sentry; 1621 SI_SA_AT_SURFACE_CUTING is the
# actor the surface-cutting command spawns (captured 2026-10-27 rejected with
# the previous 384-only gate); 385/386 are the true sentry/element upgrades and
# 2091 ECA_OBERON_GUARD the Oberon guard. Every request stays owner-bound and
# strictly decoded; the spawn dump keeps recording unrecognized templates.
EVE_SUMMON_TEMPLATES=frozenset((384,385,386,1621,2091))


def _decode(payload, uid, fields):
    if len(payload) < 4 or struct.unpack_from('>I', payload)[0] != 1:
        raise ValueError('Expected one sentry')
    dto = bytearray(0xa4)
    position = 4
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
                raise ValueError('Unsupported summon extension')
            continue
        if size == 12:
            value = b''.join(raw[i:i+4][::-1] for i in (0,4,8))
        else:
            value = (int.from_bytes(raw, 'big') ^ xor).to_bytes(size, 'little')
        dto[offset:offset+size] = value
    if position != len(payload):
        raise ValueError('Trailing summon bytes')
    if struct.unpack_from('<i', dto)[0] != -1 or struct.unpack_from('<i', dto, 4)[0] not in EVE_SUMMON_TEMPLATES:
        raise ValueError('Unverified summon template')
    if struct.unpack_from('<q', dto, 0x6d)[0] != uid:
        raise ValueError('Summon owner mismatch')
    if not all(math.isfinite(v) and abs(v) <= 100000 for v in struct.unpack_from('<fff', dto, 9)):
        raise ValueError('Invalid summon location')
    return dto


def sentry_spawn(payload, uid, instance_key):
    # Instance identity is distinct from the 80 concurrent native slots.
    # Original 1AA4A40 compares actor+3D0 (including IDs above 79).
    if type(instance_key) is not int or not 16 <= instance_key < 16384:
        raise ValueError('Summon instance range')
    candidates=[]
    for fields in LAYOUTS.values():
        try:candidates.append(_decode(payload,uid,fields))
        except ValueError:continue
    if len(candidates)!=1:
        raise ValueError('Unrecognized or ambiguous sentry encoding')
    dto=candidates[0]
    # Preserve the native team, facing, level, owner and skill parameters.
    # Allocate only the instance identity; never recycle enemy slots 0..15.
    struct.pack_into('<i', dto, 0, instance_key)
    # C50040: vector<NPC>, init-map, scalar, bytes, stats-map, two maps.
    return Event(0x201, kind=0x2d0, payload=struct.pack('>I',1)+encode_npc(dto,0)+bytes(24))


def summon_ack(result=0):
    return Event(0x201, kind=0x2cf, payload=struct.pack('>i', result))


def valid_sentry_death(data, uid):
    """Audited native expiry, distinct from player-attributed enemy deaths."""
    return (data['flag']==255 and data['status']==1
            and data['source']==data['killer']==0xffffffffffffffff
            and data['last_uid']==data['extra_uid']==0
            and not data['contribution'] and not data['counters']
            and data['readiness']=={uid:0})
