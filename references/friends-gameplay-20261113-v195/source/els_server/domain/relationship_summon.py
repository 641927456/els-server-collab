"""Town-to-town soulmate summons over the original consent and scene packets."""
from dataclasses import dataclass
import sqlite3
import struct
import time
import uuid

from els_server.domain import friend_flow
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.domain.mentor_summon import _destination
from els_server.domain.pvp_registration import _binding, _envelope, _same
from els_server.protocol import relationship_summon_messages as wire
from els_server.protocol.protocol_codec import Event
from els_server.storage import relationships
from els_server.storage.local_state import scene_ready_location, validate_location
from els_server.storage.read_scope import snapshot_connection


@dataclass(eq=False)
class Invitation:
    source: object
    recipient: object
    bindings: tuple
    pair: str
    town: int
    echo: bytes
    deadline: float


def _available(actor):
    if (not current_lease(actor) or actor.phase != 'town_ready' or actor.social_overflow
            or actor.dungeon_return_pending or actor.town_warp_transition is not None
            or getattr(actor, 'relationship_summon_arrival', None) is not None
            or actor.application.world.members.get(actor) != (1, actor.active_map)
            or actor.active_map != actor.account.get_location()['map']):
        return False
    return True


def _pair(db, actor):
    account = actor.account
    return relationships.snapshot(db, account.uid, account.account_id)


def _same_pair(invite, saved):
    return (saved is not None and saved['kind'] == 8 and saved['pair_id'] == invite.pair
            and saved['peer_uid'] == invite.recipient.account.uid)


class Summons:
    def __init__(self, world):
        self.world = world
        self.pending = {}

    def _forget(self, invite):
        self.pending.pop(invite.source)
        self.pending.pop(invite.recipient)

    def cancel(self, actor):
        invite = self.pending.get(actor)
        if invite is None:
            return
        self._forget(invite)
        if current_lease(invite.source) and _same(invite.source, invite.bindings[0]):
            self.world.send(invite.source, wire.outcome(False))

    def _current(self, invite):
        return (time.monotonic() < invite.deadline
                and _available(invite.source) and _available(invite.recipient)
                and _same(invite.source, invite.bindings[0]) and _same(invite.recipient, invite.bindings[1])
                and invite.source.active_map == invite.town)

    def invite(self, actor, payload):
        town = wire.request(payload)
        if not _available(actor) or town != actor.active_map:
            raise ValueError('Relation summon source town')
        own = friend_flow.capture(actor)
        with snapshot_connection(actor.account.store.path) as db:
            db.execute('BEGIN')
            own(db)
            saved = _pair(db, actor)
            if saved is None or saved['kind'] != 8:
                raise ValueError('Relation summon requires a current soulmate')
            target = friend_flow.online(actor).get(saved['peer_uid'])
            if (target is None or not _available(target)
                    or actor in self.pending or target in self.pending):
                raise ValueError('Relation summon peer unavailable')
            friend_flow.capture(target)(db)
            _destination(db, target, town)
            location = actor.account.get_location()
            notice = wire.invitation(location, uuid.uuid4())
            # BB4F96 gives the original consent window five seconds.
            pending = Invitation(actor, target, (_binding(actor), _binding(target)),
                                 saved['pair_id'], town, notice.payload, time.monotonic() + 5)
            if not target.mailbox.try_extend((notice,)):
                raise ValueError('Relation summon peer mailbox unavailable')
            self.pending[actor] = self.pending[target] = pending
        return [wire.ack()]

    def answer(self, actor, payload, sequence):
        accepted, echo = wire.consent(payload)
        invite = self.pending.get(actor)
        if invite is None or invite.recipient is not actor or echo != invite.echo:
            return []
        if not accepted or not self._current(invite):
            self.cancel(actor)
            return []
        source = invite.source
        town = invite.town
        with snapshot_connection(actor.account.store.path) as db:
            db.execute('BEGIN')
            friend_flow.capture(source)(db)
            friend_flow.capture(actor)(db)
            if not _same_pair(invite, _pair(db, source)):
                raise ValueError('Relation summon pair ended')
            _destination(db, actor, town)
            response = wire.arrive(source.account.get_location())
        self._forget(invite)
        actor.relationship_summon_arrival = (invite, sequence, actor.active_map)
        actor.pending_map = town
        actor.phase = 'square_accepted'
        actor.inventory_town_sync_sent = False
        self.world.leave(actor)
        self.world.send(source, wire.outcome(True))
        return [response]

    def entry(self, actor, event, sequence, transition):
        invite, accepted_sequence, source = transition
        town = invite.town
        allowed = (_envelope(event) and type(sequence) is int and accepted_sequence < sequence < 2**32
                   and current_lease(actor) and _same(actor, invite.bindings[1])
                   and actor.phase == 'square_accepted' and actor.pending_map == town
                   and actor.active_map == source and actor.account.get_location()['map'] == source)
        if event.kind == 0x225:
            if not allowed or event.payload not in (struct.pack('>iB', town, 0), struct.pack('>iB', town, 1)):
                return [Event(0x201, kind=0x226, payload=struct.pack('>5i', 515, 0, 0, 0, 0))]
            return [Event(0x201, kind=0x226, payload=struct.pack('>5i', 0, town, 0, 0, 0))]
        if allowed:
            try:
                board, progress, xyz = scene_ready_location(event.payload)
                validate_location(town, board, progress, xyz)
            except ValueError:
                allowed = False
        if not allowed:
            return [Event(0x201, kind=0x228, payload=struct.pack('>i', 515))]
        return None

    def request(self, actor, event, sequence):
        if event.event_id != 0x202:
            return None
        transition = getattr(actor, 'relationship_summon_arrival', None)
        if transition is not None and event.kind in (0x225, 0x227):
            return self.entry(actor, event, sequence, transition)
        if event.kind not in (0x40a, 0x40e):
            return None
        if not _envelope(event) or type(sequence) is not int or not 0 < sequence < 2**32:
            return [wire.ack(1)] if event.kind == 0x40a else []
        invite = self.pending.get(actor)
        try:
            friend_flow.selected(actor)
            if invite is not None and not self._current(invite):
                self.cancel(actor)
                invite = None
            if event.kind == 0x40a:
                return self.invite(actor, event.payload)
            return self.answer(actor, event.payload, sequence)
        except (ValueError, sqlite3.Error):
            if event.kind == 0x40a:
                return [wire.ack(1)]
            if invite is not None and invite.recipient is actor and event.payload[1:] == invite.echo:
                self.cancel(actor)
            return []

    def expire(self, actor):
        invite = self.pending.get(actor)
        if invite is not None and not self._current(invite):
            self.cancel(actor)

