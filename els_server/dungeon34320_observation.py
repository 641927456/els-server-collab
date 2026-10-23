"""Bounded server-side diagnostic for original34320 network events; never mutates game state.

Attach before/after the EXISTING bound Application.call(business.handle, ...).
Do not wrap that bound call: Application.call has timer/after_reply semantics.
"""
import hashlib
import json
import math
import struct
import time

REQUESTS = frozenset((0x2ce, 0xad, 0xbb, 0xb3, 0xb8, 0xd0, 0xf4))
MAX_RECORDS = 512
MAX_BYTES = 1024 * 1024
MAX_SECONDS = 1800
MAX_RECORD_BYTES = 16384


def snapshot(session):
    """Copy bounded primitives only. No account methods, SQL, clock or run methods."""
    run = getattr(session, 'dungeon_run', None)
    if run is None or run.identity != 34320 or session.role != 'game':
        return None
    tag = (id(run), run.run_id, run.stage, run.part, run.visits, session.account.uid)
    if frozenset(getattr(session, 'dungeon_participants', (session.account.uid,))) != frozenset((session.account.uid,)):
        raise ValueError('incoherent_or_multiplayer')
    part = run.parts.get(run.part)
    if not isinstance(part, dict) or len(part['npcs']) > 256 or len(run.defeated) > 256:
        raise ValueError('observation state bound')
    actors = tuple((n['key'], n['template'], bool(n.get('dynamic')),
                    bool(n['active']), n.get('team', 1), bool(n['no_drop']),
                    n.get('hp'), n.get('source_index'), n.get('start_point'))
                   for n in part['npcs'])
    reserved = tuple(n['key'] for p in run.parts.values() for n in p['npcs'])
    if len(reserved) > 16384 or len(session.summon_keys) > 16384:
        raise ValueError('observation identity bound')
    drops = getattr(session, 'world_drops', {})
    if len(drops) > 1024:
        raise ValueError('observation drop bound')
    material = tuple((k, d.get('npc_key'), d.get('quantity'), bool(d.get('pickup_committed')))
                     for k, d in drops.items() if d.get('template') == 118178)
    result = dict(run_id=run.run_id, stage=run.stage, part=run.part, visits=run.visits,
                phase=session.phase, source_sha256=run.graph['source_sha256'],
                actors=actors, defeated=tuple(sorted(run.defeated)), material=material,
                owner_uid=session.account.uid,
                spawn_owners=tuple({0, 2**64-1, session.account.uid,
                                    *reserved, *session.summon_keys}),
                allowed_summons=tuple(run.graph['stages'][str(run.stage)]['allowed_summons']),
                synced=bool(session.dungeon_substage_synced),
                part_end=bool(session.part_end_notified), clear=bool(session.clear_notified))
    if (session.dungeon_run is not run or
            tag != (id(run), run.run_id, run.stage, run.part, run.visits, session.account.uid) or
            len(part['npcs']) != len(actors) or tuple(sorted(run.defeated)) != result['defeated']):
        raise ValueError('incoherent_snapshot')
    return result


def request_fields(kind, payload, state):
    """Existing pure decoders; output is a fresh dictionary, no raw body."""
    if len(payload) > 65536:
        return dict(parse='over_observation_bound')
    if kind == 0x2ce:
        from els_server.domain.dungeon_spawns import decode
        def validate(dto):
            key, template = struct.unpack_from('<ii', dto)
            if key != -1 or template not in state['allowed_summons']:
                raise ValueError('spawn identity')
            if struct.unpack_from('<Q', dto, 0x6d)[0] not in state['spawn_owners']:
                raise ValueError('spawn owner')
            if dto[8] not in (0, 1, 2) or any(dto[o] not in (0, 1) for o in (0x4e, 0x54, 0x61, 0x65, 0x66)):
                raise ValueError('spawn flag')
            if not all(math.isfinite(v) and abs(v) <= 100000 for v in struct.unpack_from('<fff', dto, 9)):
                raise ValueError('spawn point')
        rows = decode(payload, validate)
        return dict(parse='current_script_decoder', requests=[dict(
            requested_key=struct.unpack_from('<i', d)[0], template=struct.unpack_from('<i', d, 4)[0],
            xyz=list(struct.unpack_from('<fff', d, 9)), facing=d[0x65],
            creator=struct.unpack_from('<Q', d, 0x6d)[0], team=d[8],
            active=d[0x4e], ally=d[0x66]) for d in rows])
    if kind == 0xad:
        from els_server.domain.dungeon_lifecycle import death_report
        d = death_report(payload)
        actor = next((a for a in state['actors'] if a[0] == d['index']), None)
        return dict(parse='death_report', index=d['index'],
                    # flag is the attacker class; 255 alone does not prove expiry.
                    attacker_class=d['flag'], source=d['source'], killer=d['killer'],
                    xyz=list(d['xyz']), status=d['status'], hp_bits=d['hp_bits'],
                    last_uid=d['last_uid'], extra_uid=d['extra_uid'],
                    contribution_count=len(d['contribution']), counters_count=len(d['counters']),
                    readiness_count=len(d['readiness']),
                    readiness=list(sorted(d['readiness'].items()))[:4],
                    readiness_truncated=len(d['readiness']) > 4,
                    actor=actor)
    if kind in (0xbb, 0xb8) and len(payload) == 1:
        return dict(parse='part_byte', part=struct.unpack('>b', payload)[0])
    if kind == 0xf4 and len(payload) >= 4:
        return dict(parse='qid_prefix_only', qid=struct.unpack_from('>i', payload)[0])
    return dict(parse='kind_only')


def public_state(state):
    return {k: state[k] for k in ('run_id', 'source_sha256', 'stage', 'part', 'visits',
                                  'phase', 'synced', 'part_end', 'clear')}


def spawn_reply_fields(message, state):
    """Decode actual emitted fixed-mode NPC vector with the existing decoder.

    The following UID-translation vector remains opaque: no new UID decoder.
    """
    from els_server.domain.dungeon_spawns import decode
    from els_server.domain.dungeon_npcs import MODE0_FIELDS
    count = struct.unpack_from('>I', message.payload)[0]
    if not 1 <= count <= 64:
        raise ValueError('reply count')
    npc_size = sum(field[1] for field in MODE0_FIELDS)
    end = 4 + count * npc_size
    if len(message.payload) < end:
        raise ValueError('reply vector truncated')
    declared = {(a[0], a[1]) for a in state['actors']}
    def validate(dto):
        if struct.unpack_from('<ii', dto) not in declared:
            raise ValueError('reply identity not in observed state')
    rows = decode(message.payload[:end], validate)
    return [dict(key=struct.unpack_from('<i', d)[0], template=struct.unpack_from('<i', d, 4)[0],
                 facing=d[0x65], xyz=list(struct.unpack_from('<fff', d, 9))) for d in rows]


def make_record(sequence, kind, fields, before, after, messages):
    """Pure formatter. Caller retains every original message object and order."""
    if not isinstance(messages, (list, tuple)) or len(messages) > 128:
        raise ValueError('observation response bound')
    result = dict(sequence=sequence, request_kind=kind, request=fields,
                  before=public_state(before), after=public_state(after) if after else None)
    result['replies'] = [dict(event_id=m.event_id, kind=m.kind, payload_size=len(m.payload)) for m in messages]
    result['acks'] = [dict(kind=m.kind, result=struct.unpack('>i', m.payload)[0])
                      for m in messages if m.kind in (0xae, 0xbc, 0x2cf) and len(m.payload) == 4]
    result['AF_indices'] = [struct.unpack_from('>i', m.payload)[0]
                            for m in messages if m.kind == 0xaf and len(m.payload) >= 4]
    result['emitted_2D0_NPC_vectors'] = []
    for message in messages:
        if message.event_id == 0x201 and message.kind == 0x2d0:
            try:
                vector = spawn_reply_fields(message, after or before)
                result['emitted_2D0_NPC_vectors'].append(dict(parse='existing_decoder', actors=vector))
            except (ValueError, struct.error, OverflowError):
                result['emitted_2D0_NPC_vectors'].append(dict(parse='unrecognized_by_observer'))
    same = after is not None and all(before[k] == after[k] for k in ('run_id', 'source_sha256', 'stage', 'part', 'visits'))
    if same:
        old = {a[0] for a in before['actors']}
        result['new_actors'] = [a for a in after['actors'] if a[0] not in old]
        result['new_defeated_keys'] = sorted(set(after['defeated']) - set(before['defeated']))
        old_material = {d[0]: d for d in before['material']}
        result['new_material_drops'] = [d for d in after['material'] if d[0] not in old_material]
        result['new_material_pickup_committed_keys'] = [d[0] for d in after['material']
            if d[0] in old_material and not old_material[d[0]][3] and d[3]]
        result['material_quantity_semantics'] = 'null_is_unknown; never_assume_1'
        result['D0_payload_decoded'] = False
    else:
        result['transition'] = 'cursor_or_run_changed; no_cross_stage_actor_identity_inference'
    result['uid_mapping_basis'] = 'actual_2D0_NPC_vector+poststate; trailing_UID_translation_vector_not_redecoded'
    return result


class Trace34320:
    """Only own budget/log state changes; errors cannot replace business results."""
    def __init__(self, log, connection):
        self.log = log
        self.connection = connection
        self.started = None
        self.records = 0
        self.bytes = 0
        self.disabled = False

    def stop(self, reason):
        if self.disabled:
            return
        self.disabled = True
        try:
            self.log('dungeon34320_observation_terminal', connection=self.connection,
                     reason=reason, truncated=True, diagnostic_only=True,
                     records=self.records, formatted_fields_bytes=self.bytes)
        except Exception:
            pass

    def before(self, session, event, sequence):
        if self.disabled or event.event_id != 0x202 or event.kind not in REQUESTS:
            return None
        if self.records >= MAX_RECORDS or self.bytes >= MAX_BYTES:
            self.stop('record_or_byte_budget')
            return None
        try:
            state = snapshot(session)
            if state is None:
                return None
            now = time.monotonic()  # observer budget only; no game clock call/write
            if self.started is None:
                self.started = now
            if now - self.started > MAX_SECONDS:
                self.stop('time_budget')
                return None
            try:
                fields = request_fields(event.kind, event.payload, state)
            except (ValueError, struct.error, OverflowError):
                fields = dict(parse='unrecognized_by_observer')
            fields['envelope'] = dict(uid=event.uid, target_uid=event.target_uid,
                payload_mode=event.payload_mode, performers_count=len(event.performers),
                performers=list(event.performers[:4]), performers_truncated=len(event.performers) > 4,
                payload_size=len(event.payload), payload_sha256=hashlib.sha256(event.payload).hexdigest())
            return (sequence, event.kind, fields, state)
        except Exception:
            self.stop('incoherent_or_observer_error')
            return None

    def after(self, token, session, messages):
        if token is None or self.disabled:
            return
        try:
            record = make_record(*token, snapshot(session), messages)
            size = len(json.dumps(record, ensure_ascii=True, allow_nan=False).encode('utf8'))
            if size > MAX_RECORD_BYTES or self.bytes + size > MAX_BYTES:
                self.stop('record_oversize_or_byte_budget')
                return
            self.records += 1
            self.bytes += size
            self.log('dungeon34320_observation', connection=self.connection,
                     observation_version=1, **record)
        except Exception:
            self.stop('incoherent_or_observer_error')
