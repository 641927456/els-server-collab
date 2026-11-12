"""Current wedding rooms; native clients own movement and ceremony direction."""
from contextlib import closing, ExitStack
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3, struct, time, uuid

from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol.protocol_codec import encode_event
from els_server.protocol import wedding_messages as wire, dungeon_messages as dungeon
from els_server.storage import weddings, wedding_ceremonies

WORLDS = {2: 548, 3: 549, 4: 902, 5: 903}
REQUESTS = frozenset((0x88b, 0x417, 0x41f, 0x422))


@dataclass(frozen=True)
class Seat:
    actor: object
    account: object
    uid: int
    owner: int
    session: str
    source: int
    role: int
    index: int
    ticket: int
    slot: bytes


@dataclass(eq=False)
class Room:
    reservation: int
    world: int
    closes: int
    epoch: str = field(default_factory=lambda: str(uuid.uuid4()))
    members: dict = field(default_factory=dict)
    phase: str = 'waiting'
    pending: object = None


def _prepare(deliveries, response, locks):
    for p in sorted({p for p, _ in deliveries}, key=lambda p: p.account.uid):
        locks.enter_context(p.mailbox.lock)
    return _prepared_boxes(deliveries, response)


class Weddings:
    def __init__(self, world):
        self.world = world
        self.rooms = {}
        self.by_session = {}

    def room(self, s):
        return self.by_session.get(s)

    def signature(self, room):
        return (self.rooms.get(room.reservation) is room, room.epoch, room.phase,
                room.pending, tuple(room.members.items()),
                tuple(self.room(s) is room for s in room.members))

    def capture(self, s):
        from els_server.domain.equipment_chip_flow import reset_authority
        room = self.room(s)
        if room is None:
            from els_server.domain.relationship_flow import capture
            return capture(s)
        seat = room.members[s]

        def current():
            reset_authority(s)
            if (s.account is not seat.account or s.account.uid != seat.uid
                    or s.account.account_id != seat.owner or s.shop_session_id != seat.session
                    or s.phase != 'wedding_hall' or s.active_map != room.world
                    or s.pending_map != room.world or self.room(s) is not room
                    or room.members.get(s) is not seat or self.rooms.get(room.reservation) is not room
                    or s in self.world.members or self.world.dungeons.room(s) is not None
                    or s.social_overflow or s.coop_error):
                raise ValueError('Wedding current admitted actor')
            return (s.account, s.account.store, s.account.root, s.identity), (
                s.account.uid, s.account.account_id, s.shop_session_id,
                s.phase, s.active_map, s.pending_map)

        refs, values = current()

        def same():
            try:
                r, v = current()
                return v == values and all(a is b for a, b in zip(r, refs))
            except (ValueError, AttributeError, KeyError, TypeError):
                return False

        def guard(db):
            if not same():
                raise ValueError('Wedding late actor generation')
            from els_server.storage.item_actor import require_active_character
            from els_server.storage.profession_state import require_owner
            require_active_character(db, seat.uid)
            require_owner(db, seat.uid, seat.owner)
            if db.execute('SELECT town FROM location WHERE uid=?', (seat.uid,)).fetchone() != (seat.source,):
                raise ValueError('Wedding source town changed')

        return same, guard

    def _guard(self, people, room):
        captured = [self.capture(p) for p in people]
        signature = None if room is None else self.signature(room)

        def check(db):
            for same, guard in captured:
                guard(db)
            if room is not None and self.signature(room) != signature:
                raise ValueError('Wedding room changed while preparing replies')

        return check

    @staticmethod
    def _slot(s, role, index, user):
        character, location, skills, inventory = user
        full = dungeon.member(skills, character,
            inventory['items'], account_id=s.account.account_id,
            peer_port=21100 + index, wedding_role=role)
        # Shared D9DDB0: stable slot, team, native host flag, FullUser vector.
        return bytes((index, 3, int(role == 1), 1, 0, 0)) + struct.pack('>iI', 0, 1) + full + bytes(8)

    def _join(self, s, request, db, locks, user):
        if self.room(s) is not None:
            raise ValueError('Wedding actor already admitted')
        row = weddings._record(db, request['reservation'])
        now = int(time.time())
        if (row['started_at'] is not None or row['finished_at'] is not None
                or row['canceled_at'] is not None
                or not row['ends_at'] - 86340 <= now < row['ends_at'] + 60):
            raise ValueError('Wedding is not open for entry')
        saved, _ = weddings.pairing(db, row['owner'], row['account_id'])
        if saved['pair_id'] != row['pair_id']:
            raise ValueError('Wedding couple generation ended')
        uid, owner = s.account.uid, s.account.account_id
        ticket = 0
        if request['role'] == 2:
            if uid not in (row['groom'], row['bride']):
                raise ValueError('Wedding spouse entry requires actual saved spouse')
            role = 1 if uid == row['groom'] else 2
            ticket = weddings.owned_ticket(db, uid, row['id'], 277151,
                ticket=request['ticket'], now=now)['uid']
        elif request['role'] == 1:
            if uid in (row['groom'], row['bride']) or not db.execute(
                    'SELECT 1 FROM native_wedding_invites WHERE reservation=?AND guest=?',
                    (row['id'], uid)).fetchone():
                raise ValueError('Wedding invitation requires saved recipient')
            role = 3
            ticket = weddings.owned_ticket(db, uid, row['id'], 277152,
                ticket=request['ticket'], now=now)['uid']
        else:
            if uid in (row['groom'], row['bride']) or request['ticket']:
                raise ValueError('Wedding public guest identity')
            if not row['public'] and request['password'] != row['password']:
                raise ValueError('Wedding private hall password')
            role = 4
        room = self.rooms.get(row['id'])
        current = () if room is None else tuple(room.members)
        guard = self._guard((*current, s), room)
        guard(db)
        if room is not None and (room.phase != 'waiting' or room.pending is not None):
            raise ValueError('Wedding ceremony consent already in progress')
        if any(p.account.uid == uid or p.account.account_id == owner for p in current):
            raise ValueError('Wedding duplicate actor/account')
        guests = sum(seat.role in (3, 4) for seat in room.members.values()) if room else 0
        publics = sum(seat.role == 4 for seat in room.members.values()) if room else 0
        if role in (3, 4) and (guests >= 30 or role == 4 and publics >= 30 - row['reserved_seats']):
            raise ValueError('Wedding guest/reserved capacity')
        used = {seat.index for seat in room.members.values()} if room else set()
        index = role - 1 if role in (1, 2) else next(i for i in range(2, 32) if i not in used)
        if index in used:
            raise ValueError('Wedding spouse seat already occupied')
        selected = room or Room(row['id'], WORLDS[row['hall']], row['ends_at'] + 60)
        slot = self._slot(s, role, index, user)
        seats = dict(selected.members)
        seats[s] = Seat(s, s.account, uid, owner, s.shop_session_id,
            user[1]['map'], role, index, ticket, slot)
        roster = tuple(seat.slot for seat in sorted(seats.values(), key=lambda seat: seat.index))
        descriptor = dungeon.room_metadata(selected.world, 0, room_id=row['id'],
            name='Wedding', bootstrap_port=s.port_probe_port, room_type=8, state=3,
            public=bool(row['public']), maximum=32, joined=len(seats), world_id=selected.world)
        row.update(room=row['id'], guests=guests + int(role in (3, 4)))
        answer = [wire.joined(row, descriptor, roster)]
        boxes = _prepare([(p, [wire.arrived(slot)]) for p in current], answer, locks)
        guard(db)
        return answer, boxes, selected, seats

    def _depart(self, s, room, *, answer, locks, db=None):
        guard = self._guard(tuple(room.members), room) if db is not None else None
        if guard is not None:
            guard(db)
        remaining = {p: seat for p, seat in room.members.items() if p is not s}
        slots = tuple(seat.slot for seat in sorted(remaining.values(), key=lambda seat: seat.index))
        notice = wire.left(room.members[s].uid, slots)
        deliveries = [(p, [notice]) for p in remaining]
        if room.pending is not None:
            deliveries += [(p, [wire.consent_notice(False)]) for p in room.pending if p is not s]
        boxes = _prepare(deliveries, answer, locks)
        if guard is not None:
            guard(db)
        return boxes, remaining

    def _remove(self, s, room, remaining):
        self.by_session.pop(s)
        room.members = remaining
        room.pending = None
        room.epoch = str(uuid.uuid4())
        if not remaining:
            self.rooms.pop(room.reservation)

    def _return(self, s):
        s.phase = 'map_loading'
        s.pending_map = None
        s.dungeon_return_pending = True
        s.inventory_town_sync_sent = True

    def request(self, s, event, sequence):
        if event.event_id != 0x202 or event.kind not in REQUESTS:
            return None
        kind = event.kind
        locks = ExitStack()
        try:
            same, guard = self.capture(s)
            if (event.performers != (0,) or event.uid != event.target_uid
                    or event.uid != 2**64 - 1 or event.payload_mode != 0
                    or type(sequence) is not int or not 0 < sequence < 2**32):
                raise ValueError('Wedding native request envelope')
            request = wire.request(kind, event.payload)
            room = self.room(s)
            # Materialize writer-capable getters before the room transaction.
            user = (s.account.character(), s.account.get_location(), s.account.get_skills(),
                    s.account.get_inventory_snapshot()) if kind == 0x88b else None
            leaving = s.saved_user_sync() if kind == 0x417 else None
            with closing(sqlite3.connect(s.account.store.path, timeout=10)) as db, db:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE' if kind == 0x422 else 'BEGIN')
                guard(db)
                if kind == 0x88b:
                    answer, boxes, selected, seats = self._join(s, request, db, locks, user)
                else:
                    if room is None:
                        raise ValueError('Wedding current room required')
                    people = tuple(room.members)
                    guard = self._guard(people, room)
                    guard(db)
                    if kind == 0x417:
                        answer = [wire.acknowledged(0x418), leaving]
                        boxes, remaining = self._depart(s, room, answer=answer, locks=locks, db=db)
                    elif kind == 0x41f:
                        if room.phase != 'waiting' or room.pending is not None or room.members[s].role not in (1, 2):
                            raise ValueError('Wedding start requires one current spouse')
                        spouses = tuple(p for p in people if room.members[p].role in (1, 2))
                        if len(spouses) != 2:
                            raise ValueError('Wedding start requires both current spouses')
                        other = next(p for p in spouses if p is not s)
                        answer = [wire.acknowledged(0x420)]
                        boxes = _prepare([(other, [wire.consent_requested()])], answer, locks)
                        guard(db)
                    else:
                        if room.phase == 'ceremony':
                            return []
                        if room.pending is None or room.pending[1] is not s:
                            raise ValueError('Wedding answer has no current spouse request')
                        if not request['accepted']:
                            answer = [wire.consent_notice(False)]
                            boxes = _prepare([(room.pending[0], answer)], answer, locks)
                            guard(db)
                        else:
                            roster = [dict(uid=seat.uid, account=seat.owner, role=seat.role,
                                ticket=seat.ticket, session=seat.session) for seat in room.members.values()]
                            boxes = {}
                            def encode(row, changes, repeated):
                                nonlocal boxes
                                messages = {p: [*([wire.consent_notice(True)] if seat.role in (1, 2) else []),
                                    wire.ceremony_started(changes[seat.uid], refresh=seat.role in (1, 2))]
                                    for p, seat in room.members.items()}
                                boxes = _prepare([(p, events) for p, events in messages.items() if p is not s], messages[s], locks)
                                return {p.account.uid: events for p, events in messages.items()}
                            committed = wedding_ceremonies.start(db, room.reservation, roster,
                                now=int(time.time()), guard=guard, encode=encode)
                            answer = committed[s.account.uid]
                # No room or mailbox publication before successful SQL commit.
            for p, box in boxes.items():
                p.mailbox = box
            if kind == 0x88b:
                from els_server.domain.guild_agit_flow import disconnect as guild_disconnect
                guild_disconnect(s)
                selected.members = seats
                selected.epoch = str(uuid.uuid4())
                self.rooms[selected.reservation] = selected
                self.by_session[s] = selected
                s.phase = 'wedding_hall'
                s.active_map = s.pending_map = selected.world
                self.world.synchronize(s)
            elif kind == 0x417:
                self._remove(s, room, remaining)
                self._return(s)
            elif kind == 0x41f:
                room.pending = (s, other)
            elif kind == 0x422:
                room.pending = None
                if request['accepted']:
                    room.phase = 'ceremony'
            return answer
        except (ValueError, sqlite3.Error, AttributeError, KeyError, TypeError, OverflowError, StopIteration):
            if 'same' not in locals() or not same():
                return []
            if kind == 0x88b:
                descriptor = dungeon.room_metadata(0, 0, room_id=0, name='')
                return [wire.joined(None, descriptor, (), result=-1)]
            if kind in (0x417, 0x41f):
                return [wire.acknowledged(kind + 1, result=-1)]
            return [wire.ceremony_started(result=-1)]
        finally:
            locks.close()

    def disconnect(self, s):
        room = self.room(s)
        if room is None:
            return
        remaining = {p: seat for p, seat in room.members.items() if p is not s}
        pending = room.pending
        slots = tuple(seat.slot for seat in sorted(remaining.values(), key=lambda seat: seat.index))
        try:
            notice = wire.left(room.members[s].uid, slots)
            encode_event(notice)
        finally:
            # Teardown is final. The shared bounded sender marks a slow peer
            # for disconnection while still notifying the healthy recipients.
            self._remove(s, room, remaining)
        for p in remaining:
            self.world.send(p, notice)
            if pending is not None and p in pending:
                self.world.send(p, wire.consent_notice(False))

    def relay_lost(self, s):
        room = self.room(s)
        if room is None:
            return
        with ExitStack() as locks:
            messages = [wire.acknowledged(0x418), s.saved_user_sync()]
            boxes, remaining = self._depart(s, room, answer=messages, locks=locks)
            boxes.update(_prepare([(s, messages)], (), locks))
            self._remove(s, room, remaining)
            self._return(s)
            for p, box in boxes.items():
                p.mailbox = box

    def periodic(self, s):
        room = self.room(s)
        if room is not None and int(time.time()) >= room.closes:
            self._deadline(s, room)
        elif room is None:
            self._offline_deadlines(s)

    def _offline_deadlines(self, s):
        from els_server.domain.equipment_chip_flow import current_lease
        if (s.phase in ('closing', 'channels_ready') or 0x28 not in s.completed
                or not current_lease(s) or not s.item_test or s.client_build != 'dx11_260923'):
            return
        now = time.monotonic()
        if now < getattr(s, 'wedding_deadline_after', 0):
            return
        from els_server.domain.wedding_flow import _ticket_capture
        from els_server.storage.relationships import snapshot
        from els_server.protocol.relationship_messages import married
        same, own_guard = _ticket_capture(s, phases=(s.phase,))
        with ExitStack() as locks, closing(sqlite3.connect(s.account.store.path, timeout=10)) as db, db:
            if not weddings.present(db):
                s.wedding_deadline_after = now + 60
                return
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            own_guard(db)
            saved = snapshot(db, s.account.uid, s.account.account_id)
            if saved is None or not wedding_ceremonies.expire(db, s.account.uid,
                    s.account.account_id, now=int(time.time()), guard=own_guard, saved=saved):
                s.wedding_deadline_after = now + 60
                return
            app = s.application
            people = [s]
            guards = [own_guard]
            for p in app.playing.values():
                if (p is not s and p.account.uid == saved['peer_uid'] and current_lease(p)
                        and p.phase not in ('closing', 'channels_ready') and 0x28 in p.completed):
                    _, check = _ticket_capture(p, phases=(p.phase,))
                    check(db);people.append(p);guards.append(check)
            deliveries = [(p, [married(snapshot(db, p.account.uid, p.account.account_id))]) for p in people]
            boxes = _prepare(deliveries, (), locks)
            for check in guards:
                check(db)
            db.commit()
            for p, box in boxes.items():
                p.mailbox = box
            s.wedding_deadline_after = now + 60

    def _deadline(self, s, room):
        from els_server.protocol import relationship_messages as relationship_wire
        from els_server.storage.relationships import snapshot
        guard = self._guard(tuple(room.members), room)
        users = {p: (p.account.character(), p.account.get_location(), p.account.get_skills(),
                     p.account.get_inventory_snapshot()) for p in room.members}
        with ExitStack() as locks, closing(sqlite3.connect(s.account.store.path, timeout=10)) as db, db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            guard(db)
            row = weddings._record(db, room.reservation)
            wedding_ceremonies.expire(db, row['owner'], row['account_id'], now=int(time.time()), guard=guard)
            deliveries = []
            for p, seat in room.members.items():
                saved = snapshot(db, seat.uid, seat.owner)
                messages = []
                if seat.role in (1, 2):
                    messages.append(relationship_wire.married(saved))
                character, location, skills, inventory = users[p]
                character = dict(character, relationship=saved)
                messages += [wire.acknowledged(0x418), dungeon.return_user_sync(
                    location, skills, inventory['balances'],
                    inventory['items'], character)]
                deliveries.append((p, messages))
            boxes = _prepare(deliveries, (), locks)
            guard(db)
            db.commit()
            for p in tuple(room.members):
                self.by_session.pop(p)
                self._return(p)
            room.members.clear();room.pending=None
            self.rooms.pop(room.reservation)
            for p, box in boxes.items():
                p.mailbox = box

    def routing(self, app, room):
        """One checked roster produces all routes in this committed worker view."""
        try:
            if app.world is not self.world:
                raise ValueError('Wedding transport world')
            for p, seat in room.members.items():
                if p.application is not app or app.playing.get(seat.owner) is not p:
                    raise ValueError('Wedding transport current account')
                self.capture(p)
        except (ValueError, AttributeError, KeyError, TypeError):
            return {}
        peers = [dict(uid=seat.uid, port=21100 + seat.index) for seat in room.members.values()]
        return {seat.owner: (dict(epoch=room.epoch, uid=seat.uid, peers=peers),
            {(seat.owner, room.epoch, other.uid): (other.owner, seat.uid)
                for other in room.members.values() if other.actor is not p})
            for p, seat in room.members.items()}

    def manifest(self, app, account):
        room = self.room(app.playing.get(account))
        if room is None:
            return None
        value = self.routing(app, room).get(account)
        return None if value is None else value[0]

    def relay_target(self, app, account, epoch, target):
        value = self.manifest(app, account)
        if value is None or value['epoch'] != epoch:
            return None
        s = app.playing[account]
        peer = next((p for p in self.room(s).members if p is not s and p.account.uid == target), None)
        return None if peer is None else (peer.account.account_id, s.account.uid)

    def chat(self, s, text, now):
        from els_server.protocol import social_messages as social
        try:
            room = self.room(s)
            if room is None:
                raise ValueError('Wedding chat current room')
            guard = self._guard(tuple(room.members), room)
            with ExitStack() as locks, closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
                db.execute('BEGIN')
                guard(db)
                answer = [social.chat_ack()]
                notice = social.chat_notice(s.account.character(), s.account.account_id, text, 0)
                boxes = _prepare([(p, [notice]) for p in room.members], answer, locks)
                guard(db)
                s.chat_times.append(now)
                for p, box in boxes.items():
                    p.mailbox = box
                return answer
        except (ValueError, sqlite3.Error, AttributeError, KeyError, TypeError):
            return [social.chat_ack(-1)]
