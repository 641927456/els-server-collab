"""Native public and invited housing visits with owner-only room writers."""
from contextlib import closing
from pathlib import Path
import secrets
import sqlite3
import struct
import time
from els_server.protocol import housing_social_messages as wire
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.protocol.housing_messages import entry_request, entry_snapshot
from els_server.storage import housing_rooms, housing_access, housing_options


def context(session):
    visit = getattr(session, 'housing_visit', None)
    if visit is not None:
        return visit['owner'], visit
    own = getattr(session, 'housing_own_room', None)
    return (session.account.uid, own) if own is not None else (None, None)


def occupants(session, owner, *, ready=False):
    app = getattr(session, 'application', None)
    candidates = (session,) if app is None else tuple(app.playing.values())
    return [peer for peer in candidates if peer.phase == 'housing_ready'
            and not getattr(peer, 'released', False) and context(peer)[0] == owner
            and (not ready or context(peer)[1].get('social_ready', False))]


def roster(session, owner, *, joining=None, leaving=None):
    peers = [p for p in occupants(session, owner, ready=True) if p is not leaving]
    values = {p.account.uid for p in peers}
    if joining is not None:
        values.add(joining.account.uid)
    host = next((context(p)[1].get('host') for p in peers if context(p)[1].get('host') in values), None)
    if host is None and values:
        host = min(values)
    return ([host] + sorted(values - {host})) if host is not None else []


def project(session, db, value, owner):
    current = occupants(session, owner)
    if session not in current and len(current) >= 8:
        raise ValueError('Housing room is full')
    ids = roster(session, owner, joining=session)
    value['004']['31'] = len(ids)
    value['004']['76'] = ids
    value['004']['8e'] = ids[0]
    return value


def host_state(db, owner, clock):
    row = db.execute('SELECT account_id FROM character_owners WHERE uid=?', (owner,)).fetchone()
    if row is None:
        raise ValueError('Housing target character missing')
    account, = row
    from els_server.storage.item_actor import require_active_character
    require_active_character(db, owner)
    room = housing_rooms.snapshot(db, owner, account)
    access = housing_access.snapshot(db, owner, account)
    if room is None or not housing_access.active(access, clock):
        raise ValueError('Housing target contract is unavailable')
    return account, room


def visit_capture(session, *, leaving=False):
    from els_server.domain.housing_room_flow import identity, scene
    visit = getattr(session, 'housing_visit', None)
    if visit is None or getattr(session, 'housing_own_room', None) is not None:
        raise ValueError('Housing guest admission required')
    refs, values = identity(session)
    if (session.phase != 'housing_ready' or session.active_map != 26000 or session.pending_map != 26000
            or values != visit['values'] or any(a is not b for a, b in zip(refs, visit['refs']))):
        raise ValueError('Housing guest actor changed')
    source = visit['source_town']
    scene(session, source, visit)
    def same():
        try:
            current_refs, current_values = identity(session)
        except (ValueError, AttributeError, KeyError, TypeError):
            return False
        return (current_values == values and all(a is b for a, b in zip(refs, current_refs))
                and session.housing_visit is visit and session.phase == 'housing_ready'
                and session.active_map == session.pending_map == 26000)
    def guard(db):
        if not same():
            raise ValueError('Housing guest session generation changed')
        housing_access.owner(db, values[0], values[1])
        from els_server.storage.item_actor import require_active_character
        require_active_character(db, values[0])
        if db.execute('SELECT town FROM location WHERE uid=?', (values[0],)).fetchone() != (source,):
            raise ValueError('Housing guest return location changed')
        if not leaving:
            account, room = host_state(db, visit['owner'], int(time.time()))
            if account != visit['owner_account'] or visit.get('floor', 0) not in dict(room['layout']):
                raise ValueError('Housing guest target changed')
    return same, guard, refs, values, source, False


def capture(session, *, leaving=False):
    if getattr(session, 'housing_visit', None) is not None:
        return visit_capture(session, leaving=leaving)
    if getattr(session, 'housing_own_room', None) is not None:
        from els_server.domain.housing_room_flow import capture as own_capture
        return own_capture(session)
    if session.phase == 'guild_agit_ready':
        from els_server.domain.guild_agit_flow import bank_capture
        from els_server.domain.housing_room_flow import identity
        same, guard = bank_capture(session)
        refs, values = identity(session)
        return same, guard, refs, values, session.account.get_location()['map'], False
    from els_server.domain.housing_access_flow import capture as town_capture
    from els_server.domain.housing_room_flow import identity, scene
    same, guard = town_capture(session)
    refs, values = identity(session)
    source = session.account.get_location()['map']
    scene(session, source, None)
    return same, guard, refs, values, source, False


def current_peer(peer, owner):
    if context(peer)[0] != owner:
        raise ValueError('Housing peer room changed')
    return capture(peer)


def row(db, peer, xyz):
    from els_server.storage.seal_quests import load_character
    from els_server.storage.titles import equipped
    from els_server.storage.character_custom import actor_snapshot
    from els_server.storage.inventory_state import load_items
    from els_server.storage.achievements import statuses
    character = load_character(db, peer.account.uid, peer.account.account_id, identity_only=True)
    from els_server.storage.guild_membership_state import snapshot as guild_snapshot
    character['guild_membership'] = guild_snapshot(db, peer.account.uid, peer.account.account_id)
    character['achievement_status'] = statuses(db, peer.account.account_id, (peer.account.uid,))[peer.account.uid]
    character['title'] = equipped(db, peer.account.uid)
    character['character_custom'] = actor_snapshot(db, peer.account.uid, peer.account.account_id)
    if character['unit_type'] == 10:
        from els_server.storage.luciel_state import active_state
        character['luciel_active_unit'] = active_state(db, peer.account.uid)['active_unit']
    return character, xyz, load_items(db, peer.account.uid)


def invitations(session):
    app = getattr(session, 'application', None)
    return {} if app is None else getattr(app, '_housing_invitations', {})


def invited(session, owner):
    saved = invitations(session).get((session.account.uid, owner))
    if saved is None or saved[1] != session.shop_session_id:
        return False
    app = session.application
    return any(peer.account.uid == owner and peer.shop_session_id == saved[0]
               and not peer.released for peer in app.playing.values())


def departure_boxes(session):
    owner, old = context(session)
    if old is None or not old.get('social_ready'):
        return {}
    from els_server.domain.party_commands import _prepared_boxes
    peers = [peer for peer in occupants(session, owner, ready=True) if peer is not session]
    ids = roster(session, owner, leaving=session)
    return _prepared_boxes([(peer, [wire.removed(session.account.uid, ids)]) for peer in peers], [])


def apply_departure(session, boxes, *, owner=None):
    if owner is None:
        owner, _ = context(session)
    ids = roster(session, owner, leaving=session)
    for peer, mailbox in boxes.items():
        peer.mailbox = mailbox
        peer_room = context(peer)[1]
        if peer_room is not None:
            peer_room['host'] = ids[0] if ids else 0
    _, old = context(session)
    if old is not None:
        old['social_ready'] = False


def disconnect(session):
    app = getattr(session, 'application', None)
    if app is not None and hasattr(app, '_housing_invitations'):
        uid = session.account.uid
        app._housing_invitations = {key: value for key, value in app._housing_invitations.items() if uid not in key}
    boxes = departure_boxes(session)
    apply_departure(session, boxes)
    session.housing_visit = None


def _enter(session, event, sequence, request):
    same, guard, refs, values, source, _ = capture(session, leaving=True)
    app = getattr(session, 'application', None)
    if app is None:
        raise ValueError('Housing visits require the shared online world')
    with closing(sqlite3.connect(Path(refs[1].path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        guard(db)
        clock = int(time.time())
        owner = request['target']
        if request['kind'] == 4:
            candidates = []
            for target in housing_options.public_owners(db):
                if target == values[0]:
                    continue
                try:
                    account, room = host_state(db, target, clock)
                    if housing_options.snapshot(db, target, account)['public'] and len(occupants(session, target)) < 8:
                        candidates.append(target)
                except ValueError:
                    continue
            if not candidates:
                raise ValueError('No public housing is available')
            owner = secrets.choice(candidates)
        if owner == values[0]:
            raise ValueError('Housing target is not another character')
        account, room = host_state(db, owner, clock)
        if not housing_options.snapshot(db, owner, account)['public'] and not invited(session, owner):
            raise ValueError('Housing target is private and no invitation exists')
        from els_server.storage.seal_quests import load_character
        character = load_character(db, owner, account, identity_only=True)
        value = housing_rooms.dto(character, db=db, account=account)
        # BDF250 copies the own-room flag 1C4 into HousingManager+1A0.
        # Native 32919B0 applies layout broadcasts to guests when it is false.
        value['1c4'] = False
        project(session, db, value, owner)
        answer = [Event(0x201, kind=0x924, payload=entry_snapshot(value))]
        boxes = departure_boxes(session)
        if getattr(session, 'guild_agit', None) is not None:
            from els_server.domain.guild_agit_flow import departure_boxes as guild_departure
            boxes.update(guild_departure(session, db))
        for reply in answer:
            encode_event(reply)
        guard(db)
    apply_departure(session, boxes)
    session.housing_own_room = None
    session.guild_agit = None
    session.housing_visit = dict(owner=owner, owner_account=account, refs=refs, values=values,
                                 source_town=source, floor=0, social_ready=False, host=value['004']['8e'])
    session.phase = 'housing_ready'
    session.active_map = session.pending_map = 26000
    return answer


def _ready(session, event):
    from els_server.protocol.housing_population_messages import request
    xyz = request(event.payload)
    same, guard, refs, values, _, _ = capture(session)
    owner, own = context(session)
    peers = [peer for peer in occupants(session, owner, ready=True) if peer is not session]
    from els_server.domain.party_commands import _prepared_boxes
    with closing(sqlite3.connect(refs[1].path)) as db:
        db.execute('BEGIN')
        guard(db)
        host_state(db, owner, int(time.time()))
        own_row = row(db, session, xyz)
        ids = roster(session, owner, joining=session)
        answer = [wire.population([row(db, peer, context(peer)[1]['xyz']) for peer in peers] + [own_row])]
        boxes = _prepared_boxes([(peer, [wire.added(own_row, ids)]) for peer in peers] if not own.get('social_ready') else [], answer)
        for peer in peers:
            current_peer(peer, owner)[1](db)
        guard(db)
    for peer, mailbox in boxes.items():
        peer.mailbox = mailbox
    own.update(social_ready=True, xyz=xyz, host=ids[0])
    return answer


def _options(session, event, sequence):
    if getattr(session, 'housing_visit', None) is not None:
        return [wire.options_ack(2436)]
    _, guard, refs, values, _, _ = capture(session)
    if getattr(session, 'housing_own_room', None) is None:
        raise ValueError('Housing options require the owner inside their room')
    name, public = wire.text_request(event.payload, option=True)
    owner = values[0]
    peers = occupants(session, owner, ready=True)
    from els_server.domain.party_commands import _prepared_boxes
    with closing(sqlite3.connect(refs[1].path)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        guard(db)
        host_state(db, owner, int(time.time()))
        operation = values[2] + ':housing-options:' + str(owner) + ':' + str(sequence)
        housing_options.save(db, owner, values[1], name, public, operation, event.payload)
        value = housing_rooms.dto(session.account.character(), db=db, account=values[1])
        notice = wire.options_notice(value)
        answer = [wire.options_ack(), notice]
        boxes = _prepared_boxes([(peer, [notice]) for peer in peers if peer is not session], answer)
        for peer in peers:
            current_peer(peer, owner)[1](db)
        guard(db)
    for peer, mailbox in boxes.items():
        peer.mailbox = mailbox
    return answer


def _invite(session, event):
    _, guard, refs, values, _, _ = capture(session)
    if getattr(session, 'housing_own_room', None) is None or getattr(session, 'application', None) is None:
        raise ValueError('Housing invitations require the online owner')
    name = wire.text_request(event.payload)
    target = next((peer for peer in session.application.playing.values() if not peer.released
                   and peer.account.uid != values[0] and peer.account.character()['name'].casefold() == name.casefold()), None)
    if target is None:
        raise ValueError('Housing invitation target is offline')
    target_guard = capture(target, leaving=True)[1]
    from els_server.domain.party_commands import _prepared_boxes
    answer = [wire.invite_ack(name, target.account.uid)]
    notice = wire.invite_ack(session.account.character()['name'], values[0])
    notice = Event(0x201, kind=0x934, payload=notice.payload)
    already = invitations(session).get((target.account.uid, values[0])) == (session.shop_session_id, target.shop_session_id)
    boxes = _prepared_boxes([(target, [notice])] if not already else [], answer)
    with closing(sqlite3.connect(refs[1].path)) as db:
        db.execute('BEGIN')
        guard(db)
        host_state(db, values[0], int(time.time()))
        target_guard(db)
    for peer, mailbox in boxes.items():
        peer.mailbox = mailbox
    pending = dict(invitations(session))
    pending[(target.account.uid, values[0])] = (session.shop_session_id, target.shop_session_id)
    session.application._housing_invitations = pending
    return answer


def _list(session, event):
    if event.payload:
        raise ValueError('Housing invitation list request is empty')
    _, guard, refs, values, _, _ = capture(session, leaving=True)
    rows = []
    with closing(sqlite3.connect(refs[1].path)) as db:
        db.execute('BEGIN')
        guard(db)
        for target, owner in sorted(invitations(session)):
            if target != values[0] or not invited(session, owner):
                continue
            try:
                account, _ = host_state(db, owner, int(time.time()))
            except ValueError:
                continue
            name, = db.execute('SELECT name FROM characters WHERE uid=?', (owner,)).fetchone()
            options = housing_options.snapshot(db, owner, account)
            count = len(occupants(session, owner))
            rows.append((owner, name, options['name'], count, count < 8))
        answer = [wire.invitation_list(rows)]
        for reply in answer:
            encode_event(reply)
        guard(db)
        return answer


def handle(session, event, sequence):
    if event.event_id != 0x202:
        return None
    owner, own = context(session)
    visit = getattr(session, 'housing_visit', None)
    relevant = event.kind in (0x930, 0x932, 0x93b) or event.kind == 0x923
    relevant = relevant or own is not None and event.kind in (0x92e, 0x92b, 0x490, 0x233, 0x225, 0x4fb)
    relevant = relevant or visit is not None and event.kind in (0x227, 0x935, 0xa38, 0xa3a, 0xd37)
    if not relevant:
        return None
    try:
        if (event.performers != (0,) or event.uid != event.target_uid or event.uid != 2**64-1
                or event.payload_mode != 0 or type(sequence) is not int or not 1 <= sequence < 2**32):
            raise ValueError('Housing social native envelope')
        if event.kind == 0x923:
            request = entry_request(event.payload)
            if request['kind'] == 1:
                return None
            return _enter(session, event, sequence, request)
        if event.kind == 0x93b:
            return _options(session, event, sequence)
        if event.kind == 0x930:
            return _invite(session, event)
        if event.kind == 0x932:
            return _list(session, event)
        if event.kind == 0x92e:
            return _ready(session, event)
        if event.kind in (0x935, 0xa38, 0xa3a, 0xd37):
            if event.kind == 0x935:
                from els_server.protocol.housing_layout_messages import save_ack, empty_layout
                return [save_ack(empty_layout(), result=-1)]
            if event.kind == 0xd37:
                from els_server.protocol.housing_preset_messages import acknowledgement
                return [acknowledgement((0, '', -1, [], []), result=-1)]
            from els_server.protocol.housing_pet_messages import placement_ack
            return [placement_ack(-1, [], kind=event.kind+1)]
        if event.kind == 0x92b:
            from els_server.protocol.housing_layout_messages import movement_floor
            floor = movement_floor(event.payload)
            _, guard, refs, _, _, _ = capture(session)
            with closing(sqlite3.connect(refs[1].path)) as db:
                db.execute('BEGIN')
                guard(db)
                if visit is not None:
                    room = host_state(db, owner, int(time.time()))[1]
                else:
                    from els_server.storage.housing_expansions import require_room
                    room = require_room(db, session.account.uid, session.account.account_id,
                                        own['generation'], own['operation'], int(time.time()))
                if floor not in dict(room['layout']):
                    raise ValueError('Housing movement uses an unowned floor')
                from els_server.domain.party_commands import _prepared_boxes
                peers = [peer for peer in occupants(session, owner, ready=True) if peer is not session]
                notice = wire.moved(session.account.uid, event.payload)
                boxes = _prepared_boxes([(peer, []) for peer in peers], [])
                encode_event(notice)
                for mailbox in boxes.values():
                    mailbox.append(notice, session.account.uid)
                for peer in peers:
                    current_peer(peer, owner)[1](db)
                guard(db)
            for peer, mailbox in boxes.items():
                peer.mailbox = mailbox
            own['floor'] = floor
            own['xyz'] = struct.unpack_from('>fff', event.payload)
            return []
        if event.kind == 0x4fb or visit is None:
            boxes = departure_boxes(session)
            if event.kind == 0x4fb:
                from els_server.domain.guild_agit_flow import handle as leave_handler
            else:
                from els_server.domain.housing_room_flow import handle as leave_handler
            answer = leave_handler(session, event, sequence)
            if context(session)[0] != owner or session.phase != 'housing_ready':
                apply_departure(session, boxes, owner=owner)
                session.housing_visit = None
            return answer
        same, guard, refs, _, source, _ = capture(session, leaving=True)
        with closing(sqlite3.connect(refs[1].path)) as db:
            db.execute('BEGIN')
            guard(db)
            if event.kind == 0x227:
                from els_server.storage.local_state import scene_ready_location
                scene_ready_location(event.payload)
                return [Event(0x201, kind=0x228, payload=bytes(4))]
            expected = struct.pack('>iB', source, 0) if event.kind == 0x225 else b''
            if event.payload != expected:
                raise ValueError('Housing guest exit payload')
            boxes = departure_boxes(session)
            guard(db)
        apply_departure(session, boxes)
        session.housing_visit = None
        session.phase = 'map_loading' if event.kind == 0x233 else 'town_ready'
        session.active_map = session.pending_map = source
        return None
    except (ValueError, sqlite3.Error, OverflowError, UnicodeError, KeyError, AttributeError, TypeError):
        if event.kind == 0x93b:
            return [wire.options_ack(2436)]
        if event.kind == 0x930:
            return [wire.invite_ack(result=2436)]
        if event.kind == 0x932:
            return [wire.invitation_list([])]
        if event.kind == 0x923:
            value = housing_rooms.dto(session.account.character())
            value['000'] = 2436
            return [Event(0x201, kind=0x924, payload=entry_snapshot(value))]
        if event.kind == 0x92e:
            return [wire.population([], result=2436)]
        if event.kind == 0x227:
            return [Event(0x201, kind=0x228, payload=struct.pack('>i', 515))]
        return []


def chat(session, text, now):
    from els_server.protocol import social_messages
    from els_server.domain.party_commands import _prepared_boxes
    try:
        _, guard, refs, _, _, _ = capture(session)
        owner, _ = context(session)
        peers = occupants(session, owner, ready=True)
        notice = social_messages.chat_notice(session.account.character(), session.account.account_id, text)
        boxes = _prepared_boxes([(peer, [notice]) for peer in peers], [])
        with closing(sqlite3.connect(refs[1].path)) as db:
            db.execute('BEGIN')
            guard(db)
            for peer in peers:
                current_peer(peer, owner)[1](db)
    except (ValueError, sqlite3.Error, AttributeError, KeyError, TypeError):
        return [social_messages.chat_ack(-1)]
    for peer, mailbox in boxes.items():
        peer.mailbox = mailbox
    session.chat_times.append(now)
    return [social_messages.chat_ack()]


def layout_boxes(session, db, layout, selected):
    from els_server.domain.party_commands import _prepared_boxes
    owner, _ = context(session)
    peers = [peer for peer in occupants(session, owner, ready=True) if peer is not session]
    notice = wire.layout_notice(layout, selected)
    boxes = _prepared_boxes([(peer, [notice]) for peer in peers], [])
    for peer in peers:
        current_peer(peer, owner)[1](db)
    return boxes
