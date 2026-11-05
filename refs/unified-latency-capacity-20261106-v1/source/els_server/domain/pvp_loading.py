"""Real offered pair -> original34B -> both91 -> native96 lifecycle.

This module does not decide a result or manufacture damage/death. Its room
uses the existing opaque relay transport and fixed original member payloads.
Native rendering, combat, animation and timer effects remain in the client.
"""
from dataclasses import dataclass, field
import json
import secrets
import struct
import time
from els_server.domain import pvp_actor
from els_server.domain.pvp_registration import _binding, _same, _envelope
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import pvp_room_messages as room_wire
from els_server.protocol import pvp_loading_messages as wire
from els_server.protocol import pvp_play_messages as play_wire
from els_server.protocol import social_messages


@dataclass(eq=False)
class Room:
    identity: int
    seed: str
    members: tuple
    tickets: tuple
    map_id: int
    slots: tuple
    signatures: tuple
    phase: str = 'loading'
    progress: dict = field(default_factory=dict)
    loaded: frozenset = frozenset()
    started: float | None = None


def _inventory_signature(s):
    # Bind all actual member DTO input. No equipment estimate is used as a
    # replacement for a native stat or an authoritative maximum HP.
    return json.dumps((s.account.character(), s.account.get_skills(),
                       s.account.get_inventory_snapshot()['items']),
                      sort_keys=True, separators=(',', ':'), default=_json_value)


def _json_value(value):
    if isinstance(value, (bytes, bytearray)):
        return {'bytes': bytes(value).hex()}
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError('Unserializable native member source')


class Loading:
    def __init__(self, world, registrations):
        self.world = world
        self.registrations = registrations
        self.rooms = {}

    def room(self, s):
        return self.rooms.get(s)

    def current(self, s, room):
        if (self.rooms.get(s) is not room or s not in room.members
                or room.phase not in ('loading', 'active', 'reporting', 'result')
                or s.phase != {'loading':'pvp_loading', 'active':'pvp_active',
                               'reporting':'pvp_reporting', 'result':'pvp_result'}[room.phase]
                or s.active_map != room.map_id or s.pending_map != room.map_id
                or self.world.dungeons.room(s) is not None
                or s in self.world.party_of or s in self.world.members):
            raise ValueError('PvP original current match/phase/map')
        ticket = next(t for t in room.tickets if t.session is s)
        if not _same(s, ticket.binding):
            raise ValueError('PvP original match actor changed')
        pvp_actor.actor(self.world, s)

    def admit(self, s, event, bootstrap_port):
        reg = self.registrations
        offer, confirmed = reg.confirmation(s, event)
        members = tuple(t.session for t in offer.tickets)
        guards = tuple(pvp_actor.capture(self.world, m) for m in members)
        source = reg.signature()
        def town_source():
            return (tuple(self.world.members.items()),
                    tuple((key, id(value), tuple(value.items()))
                          for key,value in self.world.towns.items()))
        original_towns = town_source()
        peers = {other for m in members
                 for other in self.world.towns[self.world.members[m]]
                 if other not in members}
        peer_guards = tuple(pvp_actor.capture(self.world, peer) for peer in peers)
        if len(confirmed) != 2:
            for guard in guards:
                guard()
            if reg.signature() != source:
                raise ValueError('PvP confirmation source changed')
            offer.confirmations = confirmed
            return []
        excluded = set().union(*confirmed.values())
        choices = tuple(sorted(room_wire.TEAM_MAPS-excluded))
        if not choices:
            raise ValueError('PvP no mutually allowed current map')
        selected = secrets.choice(choices)
        signatures = tuple(_inventory_signature(m) for m in members)
        captures = {}
        admission = room_wire.admission(members, offer.identity, selected,
                                        bootstrap_port, member_captures=captures)
        slots = tuple(bytes((i,4,int(i==0),1,0,0))+struct.pack('>iI',i,1)
                      + captures[m][0]+bytes(8) for i,m in enumerate(members))
        # Ensure these are the exact native slots placed in the actual34B.
        base = room_wire.room_info(offer.identity, selected, bootstrap_port)
        if admission.payload != base+struct.pack('>I',2)+b''.join(slots)+bytes(12):
            raise ValueError('PvP admission/captured slot mismatch')
        # Prepare old-town peer removal and private34B before any membership
        # change. No overflow/late encoder can leave a half-admitted pair.
        deliveries = [(m, (admission,)) for m in members]
        for key in {self.world.members[m] for m in members}:
            removed = [m.account.uid for m in members if self.world.members[m] == key]
            notice = social_messages.town_members(removed=removed)
            for other in self.world.towns[key]:
                if other not in members:
                    deliveries.append((other, (notice,)))
        boxes = _prepared_boxes(deliveries, ())
        for guard in guards+peer_guards:
            guard()
        if (reg.signature() != source or tuple(_inventory_signature(m) for m in members) != signatures
                or any(not reg.current(t) for t in offer.tickets)
                or any(m in self.rooms for m in members)):
            raise ValueError('PvP late admitted sources changed')
        for guard in guards+peer_guards:
            guard()
        if town_source() != original_towns:
            raise ValueError('PvP old-town membership changed during admission')
        room = Room(offer.identity, offer.generation, members, offer.tickets,
                    selected, slots, signatures)
        # All state transitions below are in-memory assignments on the one
        # Application worker; every fallible reader/encoder ran above.
        for m in members:
            key = self.world.members.pop(m)
            old = self.world.towns[key]
            old.pop(m)
            if not old:
                self.world.towns.pop(key)
            reg.offers.pop(m)
            reg.gates.pop(m, None)
            self.rooms[m] = room
            m.phase = 'pvp_loading'
            m.active_map = m.pending_map = selected
        for m, box in boxes.items():
            m.mailbox = box
        return []

    def progress(self, s, event):
        if not _envelope(event):
            raise ValueError('PvP original progress envelope')
        room = self.rooms.get(s)
        if room is None:
            raise ValueError('PvP progress has no admitted room')
        for m in room.members:
            self.current(m, room)
        value = wire.progress_request(event.payload)
        if room.phase != 'loading':
            # Only the exact duplicate final load can be retried after start.
            if room.phase == 'active' and value == 100 and s in room.loaded:
                return pvp_actor.failed(pvp_actor.safe_capture(self.world,s),
                                        lambda:[wire.progress_ack(100)])
            raise ValueError('PvP progress after loading')
        previous = room.progress.get(s, 0)
        if value < previous:
            raise ValueError('PvP regressing loading progress')
        guards = tuple(pvp_actor.capture(self.world, m) for m in room.members)
        before = (room.phase, tuple(room.progress.items()), room.loaded,
                  room.started, tuple(self.rooms.items()), room.slots)
        progress = {**room.progress, s:value}
        loaded = frozenset(m for m in room.members if progress.get(m) == 100)
        response = [wire.progress_ack(value)]
        notices = [] if value == previous else [wire.progress_notice(s.account.uid,value)]
        start = len(loaded) == 2
        if start:
            if tuple(_inventory_signature(m) for m in room.members) != room.signatures:
                raise ValueError('PvP member equipment changed during loading')
            notices += [wire.play_start(room.slots), play_wire.remaining_time(300)]
        deliveries = [(m,tuple(notices)) for m in room.members if notices]
        boxes = _prepared_boxes(deliveries, response)
        for guard in guards:
            guard()
        for m in room.members:
            self.current(m,room)
        if before != (room.phase,tuple(room.progress.items()),room.loaded,
                      room.started,tuple(self.rooms.items()),room.slots):
            raise ValueError('PvP late loading generation changed')
        if start and tuple(_inventory_signature(m) for m in room.members) != room.signatures:
            raise ValueError('PvP late native member input changed')
        for guard in guards:
            guard()
        started = time.monotonic() if start else None
        room.progress = progress
        room.loaded = loaded
        if start:
            room.started = started
            room.phase = 'active'
            for m in room.members:
                m.phase = 'pvp_active'
        for m,box in boxes.items():
            m.mailbox = box
        return response

    def manifest(self, app, account_id):
        s = app.playing.get(account_id)
        room = self.rooms.get(s)
        if room is None:
            return None
        try:
            for m in room.members:
                self.current(m, room)
                if m.application is not app:
                    return None
        except (ValueError,AttributeError,KeyError,TypeError):
            return None
        return dict(epoch=room.seed,uid=s.account.uid,
                    peers=[dict(uid=m.account.uid,port=21100+i) for i,m in enumerate(room.members)])

    def relay_target(self, app, account_id, epoch, target):
        manifest = self.manifest(app, account_id)
        if manifest is None or manifest['epoch'] != epoch:
            return None
        s = app.playing[account_id]
        room = self.rooms[s]
        other = next((m for m in room.members if m is not s and m.account.uid == target),None)
        return None if other is None else (other.account.account_id,s.account.uid)
