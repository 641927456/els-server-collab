"""Actual finite town registration/cancel and real-opponent offers.

All methods are called by Application's serialized worker. Only the current
native 7D4(mode5) -> 342 -> 349 -> 34A path can establish an offer. Queue
entries are scoped to the original connection and registration UUID. No NPC,
synthetic opponent, win, elapsed match, or task counter is introduced here.
"""
from dataclasses import dataclass
import math
import sqlite3
import struct
import time
import uuid
from els_server.domain import pvp_actor
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import pvp_match_messages as wire
from els_server.protocol import pvp_play_messages as play_wire
from els_server.protocol.protocol_codec import Event
from els_server.storage import pvp_official_profiles as profiles

ENABLED = True


@dataclass(frozen=True)
class Ticket:
    session: object
    generation: str
    binding: tuple
    operation: str
    profile: object
    queued_at: float


@dataclass(eq=False)
class Offer:
    identity: int
    generation: str
    tickets: tuple
    confirmations: dict


def _binding(s):
    a = s.account; app = s.application; root = a.root
    return ((s, a, a.store, a.characters, root, root.characters,
             root.character_accounts, app, app.accounts, app.playing, app.registry,
             s.identity, app.world),
            (a.account_id, a.uid, s.shop_session_id, str(a.store.path),
             str(a.characters.path), s.identity['id']))


def _same(s, binding):
    refs, values = _binding(s)
    return values == binding[1] and all(a is b for a, b in zip(refs, binding[0]))


def _envelope(event):
    return (event.event_id == 0x202 and event.payload_mode == 0
        and event.uid == event.target_uid == 0xffffffffffffffff
        and event.performers in ((), (0,)))


class Registrations:
    def __init__(self, world):
        self.world = world
        self.gates = {}
        self.queue = {}
        self.offers = {}
        self.wait_samples = ()

    def signature(self):
        return (id(self.gates), tuple(self.gates.items()),
            id(self.queue), tuple(self.queue.items()), id(self.offers),
            tuple((s, o, tuple(o.confirmations.items())) for s, o in self.offers.items()),
            self.wait_samples)

    def current(self, ticket):
        s = ticket.session
        try:
            pvp_actor.town(self.world, s)
            if not _same(s, ticket.binding):
                return False
            current = profiles.cold(s.account.store.path, s.account.uid, s.account.account_id)
            return current is not None and current[0] == ticket.profile
        except (ValueError, AttributeError, KeyError, TypeError, sqlite3.Error):
            return False

    def _prepare(self, actors, deliveries, responses):
        source = self.signature()
        guards = tuple(pvp_actor.capture(self.world, s) for s in actors)
        boxes = _prepared_boxes(deliveries, responses)
        if self.signature() != source:
            raise ValueError('PvP queue changed during encoding')
        for guard in guards:
            guard()
        return boxes

    @staticmethod
    def _publish(boxes):
        for s, box in boxes.items():
            s.mailbox = box

    def gate(self, s, event):
        if len(event.payload) != 8 or struct.unpack('>i', event.payload[:4])[0] != 5:
            return None
        reply_guard = pvp_actor.safe_capture(self.world, s)
        if reply_guard is None:
            return []
        try:
            if not ENABLED or not _envelope(event):
                raise ValueError('PvP registration held or invalid envelope')
            pvp_actor.town(self.world, s)
            if s in self.queue or s in self.offers:
                raise ValueError('PvP registration already active')
            response = [Event(0x201, kind=0x7d5, payload=struct.pack('>ii', 0, 5))]
            self._prepare((s,), (), response)
            reply_guard()
            self.gates[s] = (_binding(s), bytes(event.payload), str(uuid.uuid4()))
            return response
        except (ValueError, sqlite3.Error):
            return pvp_actor.failed(reply_guard, lambda: [Event(0x201, kind=0x7d5,
                payload=struct.pack('>ii', -1, 5))])

    def register(self, s, event, sequence):
        reply_guard = pvp_actor.safe_capture(self.world, s)
        if reply_guard is None:
            return []
        try:
            if (not ENABLED or not _envelope(event) or type(sequence) is not int
                    or not 1 <= sequence < 2**32):
                raise ValueError('PvP registration source')
            pvp_actor.town(self.world, s)
            gate = self.gates.get(s)
            if gate is None or not _same(s, gate[0]) or s in self.offers:
                raise ValueError('PvP original normal7D4 gate required')
            operation = s.shop_session_id+':pvp342:'+str(s.account.uid)+':'+str(sequence)
            existing = self.queue.get(s)
            if existing is not None and existing.operation != operation:
                raise ValueError('PvP duplicate active registration')
            source = self.signature()
            def guard():
                reply_guard()
                pvp_actor.town(self.world, s)
                if self.signature() != source or self.gates.get(s) is not gate:
                    raise ValueError('PvP original gate/queue changed')
            def encode(profile, repeat):
                guard()
                # Exact original constructor fallback is0 before observed wait
                # samples exist, not an invented positive opponent/ETA. Later
                # samples are actual elapsed successful offers in this queue.
                estimate = round(sum(self.wait_samples)/len(self.wait_samples)) if self.wait_samples else 0
                response = (wire.registration_ack(0, False, ''),
                            wire.wait_notification(estimate, ((0, 1, False),)))
                self._prepare((s,), (), response)
                return response
            profile, response, repeat = profiles.register(s.account.store.path,
                s.account.uid, s.account.account_id, event.payload, operation,
                guard=guard, encode=encode)
            if not repeat:
                self.queue[s] = Ticket(s, str(uuid.uuid4()), _binding(s), operation,
                                       profile, time.monotonic())
            return list(response)
        except (ValueError, sqlite3.Error):
            return pvp_actor.failed(reply_guard, lambda: [wire.registration_ack(-1, False, '')])

    def cancel(self, s, event):
        reply_guard = pvp_actor.safe_capture(self.world, s)
        if reply_guard is None:
            return []
        try:
            if not _envelope(event) or wire.cancellation(event.payload) != 0:
                raise ValueError('PvP normal self cancellation')
            pvp_actor.town(self.world, s)
            # Once offered, both34A confirmations own the continuation. A
            # delayed345 from the prior queue cannot cancel a newer offer.
            if s in self.offers:
                raise ValueError('PvP old queue cancellation after offer')
            ticket = self.queue.get(s)
            if ticket is not None and not self.current(ticket):
                raise ValueError('PvP retired registration')
            response = [wire.cancellation_ack(0, False, 0)]
            self._prepare((s,), (), response)
            reply_guard()
            self.queue.pop(s, None)
            self.gates.pop(s, None)
            return response
        except (ValueError, sqlite3.Error):
            return pvp_actor.failed(reply_guard, lambda: [wire.cancellation_ack(-1, False, 0)])

    def match(self):
        """Offer only two real compatible current registrations; no SQL award."""
        tickets = tuple(self.queue.values())
        for i, first in enumerate(tickets):
            if not self.current(first):
                continue
            for second in tickets[i+1:]:
                a, b = first.session, second.session
                if (a.account.account_id == b.account.account_id
                        or abs(first.profile.rating-second.profile.rating) > 400
                        or not self.current(second)):
                    continue
                generation = uuid.uuid4()
                identity = generation.int & ((1 << 63)-1)
                if not identity:
                    continue
                offer = Offer(identity, str(generation), (first, second), {})
                notice = play_wire.matched(identity)
                boxes = self._prepare((a, b), ((a, (notice,)), (b, (notice,))), ())
                if not self.current(first) or not self.current(second):
                    raise ValueError('PvP late incompatible original offer actors')
                now = time.monotonic()
                waits = (now-first.queued_at, now-second.queued_at)
                if any(not math.isfinite(n) or n < 0 for n in waits):
                    raise ValueError('PvP monotonic queue sample')
                self.queue.pop(a); self.queue.pop(b)
                self.offers[a] = self.offers[b] = offer
                self.wait_samples = (self.wait_samples+waits)[-64:]
                self._publish(boxes)
                return offer
        return None

    def confirmation(self, s, event):
        """Store one original native confirmation, never accept a detached one."""
        if not ENABLED or not _envelope(event):
            raise ValueError('PvP confirmation held or invalid envelope')
        offer = self.offers.get(s)
        if offer is None or any(self.offers.get(t.session) is not offer
                                or not self.current(t) for t in offer.tickets):
            raise ValueError('PvP both original offered actors required')
        flags, excluded, tail = wire.confirmation(event.payload)
        from els_server.protocol.pvp_room_messages import TEAM_MAPS
        if flags != (True, True, False) or tail or len(excluded) > 2 or not set(excluded) <= TEAM_MAPS:
            raise ValueError('PvP finite native ordinary confirmation')
        old = offer.confirmations.get(s)
        if old is not None and old != excluded:
            raise ValueError('PvP changed duplicate confirmation')
        # No response exists for34A until complete34B admission. The caller
        # must preencode and atomically admit once the returned set is complete.
        confirmed = dict(offer.confirmations)
        confirmed[s] = excluded
        return offer, confirmed
