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
# 2091 ECA_OBERON_GUARD the Oberon guard. 1622 SI_SA_EEP_ELECTRONIC_FIELD is the
# 电击磁场 actor (0x2CE captured 2026-10-28T18:49:34 in dungeon 33252, client
# trace 20261028-184402: the two neighboring 384/1621 requests each produced an
# updated_npc_actor_created, this one produced nothing because of the gate).
# Every request stays owner-bound and strictly decoded; the spawn dump keeps
# recording unrecognized templates. 1454 SI_HA_FERDINAND is 女王神侍's summoned
# unit: skills 25601/25604 are m_eType 13 with SA_EFFECTIVE_TIME 60 (the tooltip's
# 召唤时间60秒) and icon piece SI_HA_EEP_LINK_OVERCHARGE_ILLUSION, and 1454 is the
# only class_id 0 actor whose motion is Motion_EEP_FERDINAND. The same model under
# 6384 EN_TUNNEL_EVENT_FERDINAND is class_id 103, so it stays refused. No 0x2CE for
# 1454 has been captured yet; the entry is pinned to the client catalog, not to a
# request shape.
EVE_SUMMON_TEMPLATES=frozenset((384,385,386,1454,1621,1622,2091))


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


# The client destroys the server-spawned sentry actor when a stage transition
# rebuilds the scene from the cached population packet, and reports nothing.
# The server is the actor authority, so it re-creates the summon in the new
# room from the original request. Disable to restore the pre-fix wipe.
STAGE_SUMMON_PERSISTENCE_ENABLED=True


def retain_sentry(run, key, payload):
    if run is None or not STAGE_SUMMON_PERSISTENCE_ENABLED:return
    run.summon_payloads[key]=bytes(payload)
    # A sentry identity is never re-issued inside one run: the client's own
    # expiry report for the destroyed actor can outlive the stage rebuild and
    # would otherwise be applied to the summoned actor that took its key.
    run.summon_key_ceiling=max(getattr(run,'summon_key_ceiling',16),key+1)


def carry_summons(session):
    """Move still-live sentries out of a stage's retired identity space."""
    run=session.dungeon_run
    if run is None or not STAGE_SUMMON_PERSISTENCE_ENABLED:return
    pending=getattr(run,'summon_payloads',{})
    solo=frozenset(getattr(session,'dungeon_participants',(session.account.uid,)))==frozenset((session.account.uid,))
    run.respawn_payloads={key:payload for key,payload in pending.items()
                          if solo and key in session.summon_keys and key not in session.summon_deaths}
    run.summon_payloads={}


def respawn_summons(session):
    run=session.dungeon_run
    pending=getattr(run,'respawn_payloads',None) if run is not None else None
    if not pending:return []
    run.respawn_payloads={}
    # Late import: dungeon_spawns reaches the session's roster, not this module.
    from els_server.domain.dungeon_spawns import occupied_slots
    reply=[]
    for key,payload in sorted(pending.items()):
        if occupied_slots(session)>=80:break
        session.summon_next_key=max(session.summon_next_key,getattr(run,'summon_key_ceiling',16))
        while (session.summon_next_key in run.reserved_keys or session.summon_next_key in session.summon_keys
               or session.summon_next_key in run.summon_payloads):
            session.summon_next_key+=1
        try:notice=sentry_spawn(payload,session.account.uid,session.summon_next_key)
        except ValueError:continue
        session.summon_keys.add(session.summon_next_key)
        retain_sentry(run,session.summon_next_key,payload)
        session.summon_next_key+=1
        reply.append(notice)
    return reply
