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


MATERIAL_TEMPLATES = frozenset((118177, 118178, 118186))
MAX_MATERIAL_ROWS = 64
MAX_RECEIPT_UIDS = 16


def _integer(value, minimum=0, maximum=2**64-1, *, optional=False):
    if value is None and optional:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('observation integer bound')
    return value


def _text(value, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError('observation text bound')
    return value


def _drop_view(drops, shared_run_id):
    if not isinstance(drops, dict) or len(drops) > 1024:
        raise ValueError('observation drop bound')
    legacy, contexts = [], []
    for key, row in tuple(drops.items()):
        # Other ground items contribute only to the bounded total count. Their
        # unrelated shapes cannot suppress the three-material observation.
        if not isinstance(row, dict) or row.get('template') not in MATERIAL_TEMPLATES:
            continue
        key = _integer(key, 1, 2**31-1)
        template = _integer(row.get('template'), 1, 2**31-1)
        context = dict(owner=_integer(row.get('owner'), 1),
            shared_run_id=shared_run_id, reward_run_id=_text(row.get('run_id')),
            stage=_integer(row.get('stage'), 0, 2**31-1),
            part=_integer(row.get('part'), 0, 2**31-1, optional=True),
            visits=_integer(row.get('visits'), 0, 2**31-1, optional=True),
            source=_text(row.get('source'), optional=True),
            npc_key=_integer(row.get('npc_key'), 0, 2**31-1),
            world_key=key, drop_id=_integer(row.get('drop_id'), 1, 2**31-1), template=template,
            quantity=_integer(row.get('quantity'), 0, 2**31-1, optional=True),
            pickup_committed=bool(row.get('pickup_committed')))
        contexts.append(context)
        if template == 118178:
            # Preserve the original four-column legacy observation exactly.
            legacy.append((key, row.get('npc_key'), row.get('quantity'), bool(row.get('pickup_committed'))))
    return tuple(legacy), tuple(contexts)


def _receipt_view(receipt):
    if receipt is None:
        return None
    if not isinstance(receipt, dict):
        raise ValueError('observation receipt shape')
    items = receipt.get('items')
    uids = None
    if items is not None:
        if not isinstance(items, (list, tuple)) or len(items) > 1024:
            raise ValueError('observation receipt item bound')
        uids = tuple(_integer(item['uid'], 1) for item in items)
    replayed = receipt.get('replayed')
    if replayed is not None and type(replayed) is not bool:
        raise ValueError('observation receipt replay flag')
    return dict(dungeon_run_id=_text(receipt.get('dungeon_run_id'), optional=True),
        drop_id=_integer(receipt.get('drop_id'), 1, 2**31-1, optional=True),
        replayed=replayed, operation=None, operation_exposure='not_exposed_by_current_finite_pickup_receipt',
        item_uid_count=len(uids) if uids is not None else None,
        item_uids=list(uids[:MAX_RECEIPT_UIDS]) if uids is not None else None,
        item_uids_truncated=uids is not None and len(uids) > MAX_RECEIPT_UIDS,
        item_uids_sha256=hashlib.sha256(json.dumps(uids).encode('ascii')).hexdigest() if uids is not None else None,
        source='pickup_receipt_set_after_successful_flow_return; replay_is_not_a_new_award')


def _tag(session, run):
    owner = _integer(session.account.uid, 1)
    participants = frozenset(getattr(session, 'dungeon_participants', (owner,)))
    if not 1 <= len(participants) <= 4 or owner not in participants:
        raise ValueError('observation participant bound')
    participants = tuple(sorted(_integer(uid, 1) for uid in participants))
    return (id(run), _text(run.run_id), run.stage, run.part, run.visits, owner,
        participants, _text(getattr(session, 'reward_run_id', None), optional=True),
        session.phase, bool(session.dungeon_substage_synced), bool(session.part_end_notified),
        bool(session.clear_notified), getattr(session, 'world_drop_sequence', None))


def snapshot(session):
    """Revalidated bounded primitives, not an atomic snapshot on the business worker."""
    run = getattr(session, 'dungeon_run', None)
    if run is None or run.identity != 34320 or session.role != 'game':
        return None
    tag = _tag(session, run)
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
    receipt = getattr(session, 'pickup_receipt', None)
    material, contexts = _drop_view(drops, run.run_id)
    receipt_view = _receipt_view(receipt)
    personal = tuple(d for d in contexts if d['template'] in MATERIAL_TEMPLATES)
    result = dict(run_id=run.run_id, reward_run_id=tag[7], participants=tag[6],
                stage=run.stage, part=run.part, visits=run.visits,
                phase=session.phase, source_sha256=run.graph['source_sha256'],
                actors=actors, defeated=tuple(sorted(run.defeated)), material=material,
                personal_material_drops=personal[:MAX_MATERIAL_ROWS],
                personal_material_drop_count=len(personal),
                personal_material_drops_truncated=len(personal) > MAX_MATERIAL_ROWS,
                drop_contexts=contexts, world_drop_count=len(drops),
                pickup_receipt=receipt_view, receipt_marker=id(receipt),
                owner_uid=session.account.uid,
                spawn_owners=tuple({0, 2**64-1, *tag[6], *reserved, *session.summon_keys}),
                allowed_summons=tuple(run.graph['stages'][str(run.stage)]['allowed_summons']),
                synced=bool(session.dungeon_substage_synced),
                part_end=bool(session.part_end_notified), clear=bool(session.clear_notified),
                consistency='bounded_primitives_revalidated_not_worker_atomic')
    if (session.dungeon_run is not run or tag != _tag(session, run)
            or getattr(session, 'world_drops', {}) is not drops
            or getattr(session, 'pickup_receipt', None) is not receipt
            or _drop_view(drops, run.run_id) != (material, contexts)
            or _receipt_view(receipt) != receipt_view
            or len(part['npcs']) != len(actors) or tuple(sorted(run.defeated)) != result['defeated']):
        raise ValueError('incoherent_snapshot')
    return result


def request_fields(kind, payload, state):
    """Existing pure decoders; output is a fresh dictionary, no raw body."""
    if len(payload) > 65536:
        return dict(parse='over_observation_bound')
    if kind == 0x2ce:
        if state is None:
            return dict(parse='unknown_unavailable; no_spawn_context_decode')
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
        actor = next((a for a in state['actors'] if a[0] == d['index']), None) if state is not None else None
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
    if kind == 0xd0:
        from els_server.domain.drop_pickup import ground_pickup_request
        request = ground_pickup_request(payload)
        return dict(parse='ground_pickup_request', drop_id=request['drop_id'],
            template=request['template'], quantity=request['quantity'],
            player_xyz=list(request['player_xyz']), drop_xyz=list(request['drop_xyz']),
            native_mode=request['native_mode'], layout=request['layout'],
            issued_context=_context(state, request['drop_id'], request['template']))
    if kind in (0xbb, 0xb8) and len(payload) == 1:
        return dict(parse='part_byte', part=struct.unpack('>b', payload)[0])
    if kind == 0xf4 and len(payload) >= 4:
        return dict(parse='qid_prefix_only', qid=struct.unpack_from('>i', payload)[0])
    return dict(parse='kind_only')


def public_state(state):
    if state is None:
        return dict(status='unknown_unavailable', consistency='no_owner_run_or_actor_match_claimed')
    return {k: state[k] for k in ('run_id', 'reward_run_id', 'participants', 'owner_uid',
        'source_sha256', 'stage', 'part', 'visits', 'phase', 'synced', 'part_end', 'clear',
        'personal_material_drops', 'personal_material_drop_count',
        'personal_material_drops_truncated', 'world_drop_count', 'consistency')}


def _context(state, drop_id, template, emitted_owner=None):
    if state is None:
        return dict(issued=None, matches_current_owner_template_run=None,
            emitted_owner_matches=None, status='unknown_unavailable')
    row = next((d for d in state['drop_contexts'] if d['world_key'] == drop_id), None)
    return dict(issued=row, matches_current_owner_template_run=bool(row is not None
        and row['drop_id'] == drop_id and row['template'] == template and row['owner'] == state['owner_uid']
        and row['reward_run_id'] == state['reward_run_id']),
        emitted_owner_matches=None if emitted_owner is None else row is not None and row['owner'] == emitted_owner)


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
                  before=public_state(before), after=public_state(after))
    result['replies'] = [dict(event_id=m.event_id, kind=m.kind, payload_size=len(m.payload)) for m in messages]
    result['acks'] = [dict(kind=m.kind, result=struct.unpack('>i', m.payload)[0])
                      for m in messages if m.kind in (0xae, 0xbc, 0x2cf) and len(m.payload) == 4]
    result['AF_indices'] = [struct.unpack_from('>i', m.payload)[0]
                            for m in messages if m.kind == 0xaf and len(m.payload) >= 4]
    result['emitted_2D0_NPC_vectors'] = []
    for message in messages:
        if message.event_id == 0x201 and message.kind == 0x2d0:
            if after is None and before is None:
                result['emitted_2D0_NPC_vectors'].append(dict(parse='unknown_unavailable; no_actor_match_claimed'))
                continue
            try:
                vector = spawn_reply_fields(message, after or before)
                result['emitted_2D0_NPC_vectors'].append(dict(parse='existing_decoder', actors=vector))
            except (ValueError, struct.error, OverflowError):
                result['emitted_2D0_NPC_vectors'].append(dict(parse='unrecognized_by_observer'))
    same = before is not None and after is not None and all(before[k] == after[k] for k in ('run_id', 'source_sha256', 'stage', 'part', 'visits'))
    if same:
        old = {a[0] for a in before['actors']}
        result['new_actors'] = [a for a in after['actors'] if a[0] not in old]
        result['new_defeated_keys'] = sorted(set(after['defeated']) - set(before['defeated']))
        old_material = {d[0]: d for d in before['material']}
        result['new_material_drops'] = [d for d in after['material'] if d[0] not in old_material]
        result['new_material_pickup_committed_keys'] = [d[0] for d in after['material']
            if d[0] in old_material and not old_material[d[0]][3] and d[3]]
        result['material_quantity_semantics'] = 'null_is_unknown; never_assume_1'
        result['D0_payload_decoded'] = kind == 0xd0 and fields.get('parse') == 'ground_pickup_request'
    else:
        result['transition'] = ('unknown_unavailable; no_actor_or_material_delta_inference'
            if before is None or after is None else
            'cursor_or_run_changed; no_cross_stage_actor_identity_inference')
    result['D0_payload_decoded'] = kind == 0xd0 and fields.get('parse') == 'ground_pickup_request'
    if kind == 0xd0 and after is not None:
        receipt = after['pickup_receipt']
        fresh = before is not None and after['receipt_marker'] != before['receipt_marker']
        if (fresh and receipt is not None and receipt['drop_id'] == fields.get('drop_id')
                and receipt['dungeon_run_id'] == after['reward_run_id']):
            result['pickup_receipt'] = receipt
            result['pickup_receipt_context'] = _context(after, receipt['drop_id'], fields['template'])
        else:
            result['pickup_receipt'] = None
            result['pickup_receipt_attribution'] = 'no_fresh_matching_returned_receipt'
    result['uid_mapping_basis'] = 'actual_2D0_NPC_vector+poststate; trailing_UID_translation_vector_not_redecoded'
    return result


EGRESS_KINDS = frozenset((0xcf, 0xd2, 0xd3, 0x2d0))


def sent_fields(message, state):
    """Exact current fixed CF/D2 emitters; D3 stays size/hash-only."""
    payload = message.payload
    result = dict(payload_size=len(payload), payload_sha256=hashlib.sha256(payload).hexdigest())
    if message.kind == 0xcf:
        if len(payload) != struct.calcsize('>Iii?fIQb3f3i'):
            raise ValueError('observer CF layout')
        count, template, drop_id, left, speed, owners, owner, flag, x, y, z, a, b, c = struct.unpack('>Iii?fIQb3f3i', payload)
        if count != 1 or owners != 1 or left or speed != 0.0 or flag != 0 or (a, b, c) != (0, 0, 0):
            raise ValueError('observer CF fixed producer')
        if not all(math.isfinite(v) and abs(v) <= 1000000 for v in (x, y, z)):
            raise ValueError('observer CF point')
        result.update(parse='current_ground_drop_notice', owner_uid=owner, template=template,
            drop_id=drop_id, xyz=[x, y, z], issued_context=_context(state, drop_id, template, owner))
    elif message.kind == 0xd2:
        if len(payload) != struct.calcsize('>Qiib?QIQiib?H'):
            raise ValueError('observer D2 layout')
        owner, template, drop_id, flag, failed, opaque_uid, count, recipient, ed, bonus_ed, tail, extra, n = struct.unpack('>Qiib?QIQiib?H', payload)
        if flag != 0 or failed or opaque_uid != 0 or count != 1 or owner != recipient or ed < 0 or bonus_ed < 0 or tail != 0 or extra or n != 0:
            raise ValueError('observer D2 fixed producer')
        result.update(parse='current_ground_pickup_notice', owner_uid=owner, template=template,
            drop_id=drop_id, recipient_uid=recipient, ed=ed, bonus_ed=bonus_ed,
            issued_context=_context(state, drop_id, template, owner))
    elif message.kind == 0xd3:
        result['parse'] = 'size_hash_only_not_inventory_decode'
        result['last_pickup_receipt_hint'] = state['pickup_receipt'] if state is not None else None
        result['receipt_hint_attribution'] = 'last_flow_receipt_only_not_proof_this_D3_awarded_items'
    elif message.kind == 0x2d0:
        if state is None:
            result.update(parse='unknown_unavailable; size_hash_only_no_actor_match')
        else:
            result.update(parse='existing_decoder', actors=spawn_reply_fields(message, state))
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
        self.target_seen = False

    def _scope(self, session, *, allow_unknown=False):
        # A missing run can retain only in-flight CF/D2 facts inside the same
        # live dungeon phase. Town/other-map traffic never inherits this latch.
        if (getattr(session, 'role', None) != 'game'
                or getattr(session, 'phase', None) not in ('dungeon_loading', 'dungeon_active')):
            self.target_seen = False
            return False
        run = getattr(session, 'dungeon_run', None)
        if run is None:
            return self.target_seen and allow_unknown
        self.target_seen = getattr(run, 'identity', None) == 34320
        return self.target_seen

    def _sample(self, session):
        try:
            return snapshot(session)
        except (ValueError, AttributeError, KeyError, TypeError, RuntimeError, OverflowError):
            # Drift/refusal is an unavailable diagnostic sample, not a reason
            # to lose a successfully drained payload fact or disable the trace.
            return None

    def stop(self, reason):
        if self.disabled:
            return
        self.disabled = True
        try:
            record = dict(connection=self.connection, reason=reason, truncated=True,
                diagnostic_only=True, observation_version=2, records=self.records,
                formatted_fields_bytes=self.bytes)
            size = len(json.dumps(dict(event='dungeon34320_observation_terminal', **record),
                ensure_ascii=True, allow_nan=False).encode('utf8'))
            # A terminal line also consumes the same budget; omit it if exhausted.
            if (self.records >= MAX_RECORDS or size > MAX_RECORD_BYTES or self.bytes + size > MAX_BYTES
                    or self.started is not None and time.monotonic() - self.started > MAX_SECONDS):
                return
            self.records += 1
            self.bytes += size
            self.log('dungeon34320_observation_terminal', **record)
        except Exception:
            pass

    def _ready(self):
        if self.disabled:
            return False
        if self.records >= MAX_RECORDS or self.bytes >= MAX_BYTES:
            self.stop('record_or_byte_budget')
            return False
        now = time.monotonic()  # observer budget only; no game clock call/write
        if self.started is None:
            self.started = now
        if now - self.started > MAX_SECONDS:
            self.stop('time_budget')
            return False
        return True

    def _emit(self, name, record):
        if not self._ready():
            return
        fields = dict(connection=self.connection, observation_version=2, **record)
        size = len(json.dumps(dict(event=name, **fields), ensure_ascii=True, allow_nan=False).encode('utf8'))
        if size > MAX_RECORD_BYTES or self.bytes + size > MAX_BYTES:
            self.stop('record_oversize_or_byte_budget')
            return
        self.records += 1
        self.bytes += size
        self.log(name, **fields)

    def before(self, session, event, sequence):
        if self.disabled or event.event_id != 0x202 or event.kind not in REQUESTS:
            return None
        try:
            if not self._scope(session) or not self._ready():
                return None
            state = self._sample(session)
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
            self._emit('dungeon34320_observation', make_record(*token, self._sample(session), messages))
        except Exception:
            self.stop('incoherent_or_observer_error')

    def sent(self, session, message, wire_sequence, *, send_path, request_sequence=None, request_kind=None):
        if self.disabled:
            return
        try:
            if message.event_id != 0x201 or message.kind not in EGRESS_KINDS:
                return
            if not self._scope(session, allow_unknown=message.kind in (0xcf, 0xd2)) or not self._ready():
                return
            state = self._sample(session)
            if send_path not in ('periodic', 'request_reply', 'heartbeat'):
                raise ValueError('observer send path')
            try:
                emitted = sent_fields(message, state)
            except (ValueError, struct.error, OverflowError):
                emitted = dict(parse='unrecognized_by_observer', payload_size=len(message.payload),
                    payload_sha256=hashlib.sha256(message.payload).hexdigest())
            self._emit('dungeon34320_observation_sent', dict(wire_sequence=wire_sequence,
                event_id=message.event_id, kind=message.kind, send_path=send_path,
                triggering_request_sequence=request_sequence, triggering_request_kind=request_kind,
                attribution='actual_post_drain_egress; batch_may_include_peer_mailbox; not_client_receipt',
                state=public_state(state), emitted=emitted))
        except Exception:
            self.stop('incoherent_or_observer_error')
