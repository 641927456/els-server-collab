"""Native friend operations and saved, permission-scoped presence updates."""
from els_server.storage.read_scope import snapshot_connection
from contextlib import closing, ExitStack
from pathlib import Path
import sqlite3
from els_server.storage.read_scope import canonical_path
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import friend_messages as wire
from els_server.storage import friend_state as storage


def selected(s):
    app = s.application
    account = s.account
    if (s.released or s.role != 'game' or s.client_build != 'dx11_260923'
            or not s.item_test or not current_lease(s) or 0x28 not in s.completed
            or not app.registry.enabled(account.account_id)
            or s.identity['id'] != account.account_id):
        raise ValueError('Current authenticated friend character required')
    refs = (s.account, account.store, account.characters, account.root, s.identity,
            app, app.world, s.mailbox)
    values = (account.uid, account.account_id, s.shop_session_id)
    return refs, values


def capture(s):
    refs, values = selected(s)
    def guard(db):
        actual_refs, actual_values = selected(s)
        if actual_values != values or any(a is not b for a, b in zip(refs, actual_refs)):
            raise ValueError('Friend character or response mailbox changed')
        storage.require_owner(db, values[0], values[1])
    return guard


def online(s):
    result = {}
    path = canonical_path(s.account.store.path)
    with s.application.registry.enabled_snapshot():
        for peer in tuple(s.application.playing.values()):
            if (not peer.released and current_lease(peer)
                    and peer.phase not in ('closing', 'channels_ready')
                    and canonical_path(peer.account.store.path) == path
                    and peer.application.registry.enabled(peer.account.account_id)):
                result[peer.account.uid] = peer
    return result


def handle(s, event, sequence):
    if event.event_id != 0x202 or event.kind not in wire.REQUESTS:
        return None
    same_account, same_uid = s.account, s.account.uid
    locks = ExitStack()
    try:
        own_guard = capture(s)
        if (event.performers not in ((), (0,)) or event.uid != event.target_uid
                or event.uid != 2**64 - 1 or event.payload_mode != 0
                or type(sequence) is not int or not 1 <= sequence < 2**32):
            raise ValueError('Native friend request envelope')
        parsed = wire.request(event.kind, event.payload)
        if 'target' in parsed and not 1001 <= parsed['target'] < 2**63 - 1:
            raise ValueError('Friend target identity')
        present = online(s)
        boxes, peer_guards = {}, []
        def guard(db):
            own_guard(db)
            for peer_guard in peer_guards:
                peer_guard(db)
        def encode(db, result, notices, repeated):
            nonlocal boxes
            response = [wire.acknowledgement(event.kind, **result)]
            deliveries = []
            my = storage.character(db, uid=same_uid)
            if not repeated:
                for uid, notice in notices:
                    peer = present.get(uid)
                    if peer is None:
                        continue
                    peer_guards.append(capture(peer))
                    if notice == 'invitation':
                        message = wire.invitation(same_uid, my['name'], parsed['message'])
                    else:
                        kinds = dict(accepted=0x24d, denied=0x250, blocked=0x253,
                                     unblocked=0x256, deleted=0x259)
                        message = wire.notification(kinds[notice], same_uid, my['name'])
                    events = [message]
                    peer_state = storage.snapshot(db, uid, peer.account.account_id, present)
                    row = next((row for row in peer_state['friends'] if row['uid'] == same_uid), None)
                    if row is not None:
                        events.append(wire.positions([row]))
                    deliveries.append((peer, events))
            if result['target']:
                current = storage.snapshot(db, same_uid, s.account.account_id, present)
                row = next((row for row in current['friends'] if row['uid'] == result['target']), None)
                if row is not None:
                    response.append(wire.positions([row]))
            recipients = {s, *(peer for peer, _ in deliveries)}
            for peer in sorted(recipients, key=lambda peer: peer.account.uid):
                locks.enter_context(peer.mailbox.lock)
            boxes = _prepared_boxes(deliveries, response)
            return response
        operation = s.shop_session_id + ':friend:' + str(same_uid) + ':' + str(sequence)
        response = storage.perform(s.account.store.path, same_uid, s.account.account_id,
                                   event.kind, event.payload, parsed, operation, guard, encode)
        for peer, box in boxes.items():
            peer.mailbox = box
        return response
    except (ValueError, sqlite3.Error, UnicodeError, OverflowError):
        if s.account is not same_account or s.account.uid != same_uid or not current_lease(s):
            return []
        return [wire.acknowledgement(event.kind, result=-1)]
    finally:
        locks.close()


def synchronize(s, event, response):
    cold = any(message.event_id == 0x201 and message.kind == 0x2f for message in response)
    guild_update = any(message.event_id == 0x201 and message.kind in (0x278, 0x28b, 0x284, 0x295)
                       for message in response)
    if not cold and not guild_update and event.kind not in (0x28, 0x225, 0x227, 0x233, 0x490, 0x91, 0xb3,
                                       0x219, 0x80f, 0x67, 0x14a, 0x382, 0x34a,
                                       0x5a2, 0x5a4, 0x5b4, 0x88b, 0x417):
        return response
    if not current_lease(s) or s.phase in ('closing', 'channels_ready'):
        disconnect(s)
        return response
    present = online(s)
    with ExitStack() as locks, snapshot_connection(s.account.store.path) as db:
        db.execute('BEGIN')
        me = storage.character(db, uid=s.account.uid)
        guild = None
        if storage.exists(db, 'native_guild_members') and storage.exists(db, 'native_guilds'):
            guild = db.execute('SELECT g.id,g.name FROM native_guild_members m '
                               'JOIN native_guilds g ON g.id=m.guild_id '
                               'WHERE m.owner=? AND m.account_id=?',
                               (s.account.uid, s.account.account_id)).fetchone()
        signature = (s.account.uid, s.account.account_id, s.active_map, s.phase,
                     me['unit_class'], me['level'], guild)
        if not cold and getattr(s, 'friend_presence_signature', None) == signature:
            return response
        value = storage.snapshot(db, s.account.uid, s.account.account_id, present)
        if cold:
            from els_server.storage import mentor_relations
            saved=mentor_relations.relation(db,s.account.uid)
            partners=()if saved is None else(mentor_relations.public_info(db,saved['partner'],present.get(saved['partner']),saved=saved),)
            answer=[wire.restore(message,value,mentor_partners=partners)for message in response]
        else:answer=response
        boxes = presence_boxes(s, db, present, answer, locks)
        s.friend_presence_signature = signature
        for peer, box in boxes.items():
            peer.mailbox = box
    return answer


def presence_boxes(s, db, present, response, locks):
    deliveries = []
    if storage.exists(db, 'native_friend_edges'):
        for owner, in db.execute('SELECT mine.owner FROM native_friend_edges mine '
                                 'JOIN native_friend_edges peer ON peer.owner=mine.target AND peer.target=mine.owner '
                                 'WHERE mine.target=? AND mine.status=0 AND mine.blocked=0 '
                                 'AND peer.status=0 AND peer.blocked=0', (s.account.uid,)):
            peer = present.get(owner)
            if peer is None or peer is s:
                continue
            value = storage.snapshot(db, owner, peer.account.account_id, present)
            row = next((row for row in value['friends'] if row['uid'] == s.account.uid), None)
            if row is not None:
                deliveries.append((peer, [wire.positions([row])]))
    for peer, _ in sorted(deliveries, key=lambda delivery: delivery[0].account.uid):
        locks.enter_context(peer.mailbox.lock)
    return _prepared_boxes(deliveries, response)


def disconnect(s):
    if getattr(s, 'friend_presence_signature', None) is None:
        return
    live = s.application.playing.get(s.account.account_id)
    if live is not None and live is not s:
        # The replacement session owns this character's online subscription.
        s.friend_presence_signature = None
        return
    present = online(s)
    present.pop(s.account.uid, None)
    with ExitStack() as locks, closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri() + '?mode=ro',
                                                       uri=True, timeout=10)) as db:
        db.execute('BEGIN')
        boxes = presence_boxes(s, db, present, [], locks)
        s.friend_presence_signature = None
        for peer, box in boxes.items():
            peer.mailbox = box
