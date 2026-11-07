"""Finite one-life native death and end-report authority, before settlement.

Only the already admitted, loaded two-player room can enter this flow. The
native dying actor sends A7, then its own animation supplies empty AA. Native
AC and 9D are emitted after that completion, and each original actor supplies
its own 9E. No damage, animation, HP, winner packet, reward or quest progress
is manufactured here. The returned sealed result is input to the separately
transactional settlement; this module alone cannot award or open a match.
"""
from dataclasses import dataclass, field
import time

from els_server.domain import pvp_actor
from els_server.domain.party_commands import _prepared_boxes
from els_server.domain.pvp_registration import _envelope
from els_server.protocol import known_resurrection as death_wire
from els_server.protocol import pvp_death_messages as wire
from els_server.protocol import pvp_play_messages as play_wire


@dataclass(eq=False)
class Round:
    room: object
    seed: str
    victim: object = None
    killer: object = None
    death_sequence: int | None = None
    death_raw: bytes | None = None
    active_side: int | None = None
    completed: bool = False
    reports: dict = field(default_factory=dict)
    report_sequences: dict = field(default_factory=dict)
    ended: float | None = None
    sealed: object = None
    reason: str = 'kill'
    leaver: object = None


@dataclass(frozen=True)
class DeathResult:
    """Bound evidence, not a client-supplied result or persistent receipt."""
    seed: str
    room: object
    members: tuple
    victim: object
    killer: object
    elapsed: int
    reports: tuple
    reason: str = 'kill'
    leaver: object = None


class Rounds:
    def __init__(self, loading):
        self.loading = loading
        self.world = loading.world
        self.rounds = {}

    def _current(self, s, event=None):
        if event is not None and not _envelope(event):
            raise ValueError('PvP native round envelope')
        room = self.loading.room(s)
        if room is None or room.phase not in ('active', 'reporting'):
            raise ValueError('PvP round not active')
        for member in room.members:
            self.loading.current(member, room)
        if (len(room.members) != 2 or room.loaded != frozenset(room.members)
                or room.started is None):
            raise ValueError('PvP both original members must be loaded')
        round_ = self.rounds.get(room.seed)
        if round_ is not None and (round_.room is not room or round_.seed != room.seed):
            raise ValueError('PvP round generation reused')
        return room, round_

    def _signature(self, room, round_):
        return (id(self.rounds), tuple(self.rounds.items()),
            id(self.loading.rooms), tuple(self.loading.rooms.items()),
            room, room.identity, room.seed, room.members, room.tickets,
            room.map_id, room.slots, room.signatures, room.phase,
            tuple(room.progress.items()), room.loaded, room.started,
            None if round_ is None else (round_.room, round_.seed,
                round_.victim, round_.killer, round_.death_sequence,
                round_.death_raw, round_.active_side, round_.completed,
                tuple(round_.reports.items()), tuple(round_.report_sequences.items()),
                round_.ended, round_.sealed,round_.reason,round_.leaver))

    def _prepare(self, room, round_, deliveries, responses):
        original = self._signature(room, round_)
        guards = tuple(pvp_actor.capture(self.world, m) for m in room.members)
        boxes = _prepared_boxes(deliveries, responses)
        for member, guard in zip(room.members, guards):
            guard()
            self.loading.current(member, room)
        if self._signature(room, round_) != original:
            raise ValueError('PvP round changed during native encoding')
        for guard in guards:
            guard()
        return boxes

    @staticmethod
    def _publish(boxes):
        for member, box in boxes.items():
            member.mailbox = box

    @staticmethod
    def _sequence(sequence):
        if type(sequence) is not int or not 0 <= sequence < 2**64:
            raise ValueError('PvP authenticated transport sequence')

    def death(self, s, event, sequence):
        self._sequence(sequence)
        if event.kind != 0xa7:
            raise ValueError('PvP own dying request kind')
        room, round_ = self._current(s, event)
        request = death_wire.death_request(event.payload)
        other = next(m for m in room.members if m is not s)
        # The caller is the victim. Only the real other loaded actor can be
        # credited; NPC/template IDs, self kills and invented extra context do
        # not turn into the finite real-player first kill.
        if (request['killer'] != -1 or request['user'] != other.account.uid
                or request['maximum'] != other.account.uid):
            raise ValueError('PvP original opponent death source')
        if round_ is not None:
            if (round_.victim is not s or round_.killer is not other
                    or round_.death_raw != event.payload):
                raise ValueError('PvP conflicting one-life death')
            # A transport replay can acknowledge the already accepted death;
            # it cannot rebroadcast A9, clear reports or create another life.
            response = [death_wire.death_ack()]
            self._prepare(room, round_, (), response)
            return response
        if room.phase != 'active' or time.monotonic() - room.started >= 300:
            raise ValueError('PvP death outside the authorized live clock')
        response = [death_wire.death_ack()]
        notice = wire.killed(s.account.uid, other.account.uid, other.account.uid)
        scores=tuple((m.account.uid,int(m is other),int(m is s),int(m is other))for m in room.members)
        score_notices=wire.scores(scores,red=int(room.members[0]is other),blue=int(room.members[1]is other))
        boxes = self._prepare(room, None,
            [(member, (notice,*score_notices)) for member in room.members], response)
        # No native rebirth or server animation clock is introduced for this
        # terminal one-kill life. Native AA remains the completion source.
        round_ = Round(room, room.seed, s, other, sequence, event.payload,
                       int(request['flag']))
        self.rounds[room.seed] = round_
        self._publish(boxes)
        return response

    def complete(self, s, event):
        if event.kind != 0xaa or event.payload:
            raise ValueError('PvP native empty death completion')
        room, round_ = self._current(s, event)
        if round_ is None or round_.victim is not s:
            raise ValueError('PvP completion without original accepted death')
        if round_.completed:
            self._prepare(room, round_, (), ())
            return []
        if room.phase != 'active':
            raise ValueError('PvP death completion phase')
        end = time.monotonic()
        if end < room.started:
            raise ValueError('PvP monotonic clock regressed')
        notice = death_wire.death_complete(s.account.uid)
        request = play_wire.time_over()
        boxes = self._prepare(room, round_,
            [(member, (notice, request)) for member in room.members], ())
        round_.completed = True
        round_.ended = end
        room.phase = 'reporting'
        for member in room.members:
            member.phase = 'pvp_reporting'
        self._publish(boxes)
        return []

    def report(self, s, event, sequence):
        self._sequence(sequence)
        if event.kind != 0x9e:
            raise ValueError('PvP original end-report kind')
        room, round_ = self._current(s, event)
        if (round_ is None or not round_.completed or round_.ended is None
                or room.phase != 'reporting'):
            raise ValueError('PvP unsolicited native HP report')
        report = play_wire.hp_report(event.payload)
        if round_.reason=='kill' and s is round_.victim and (report.hp != 0 or report.active_side != round_.active_side):
            raise ValueError('PvP dying native report contradicts accepted life')
        if round_.reason=='timeout' and report.maximum_hp is None:
            raise ValueError('PvP timeout requires the original native maximum-HP support')
        prior = round_.reports.get(s)
        if prior is not None and prior.raw != report.raw:
            raise ValueError('PvP conflicting end-report retry')
        # Neither report is interpreted as a winner claim. The sole terminal
        # death already fixes the one-kill outcome. Timeout needs a separate,
        # evidenced percentage denominator and cannot call this path.
        response = [play_wire.report_ack(0)]
        self._prepare(room, round_, (), response)
        if prior is not None:
            return response
        reports = {**round_.reports, s: report}
        sealed = None
        if len(reports) == 2:
            elapsed = min(300, int(round_.ended - room.started))
            if round_.reason=='timeout':
                left,right=room.members;lv,rv=reports[left],reports[right]
                # Products of two binary32 values fit a binary64 mantissa;
                # compare actual percentages without rounding a winner.
                a,b=lv.hp*rv.maximum_hp,rv.hp*lv.maximum_hp
                killer=left if a>b else right if b>a else None
                victim=next(m for m in room.members if m is not killer)if killer else None
            else:killer,victim=round_.killer,round_.victim
            sealed = DeathResult(room.seed, room, room.members,
                victim, killer, elapsed,
                tuple((member, reports[member]) for member in room.members),round_.reason)
        round_.reports = reports
        round_.report_sequences = {**round_.report_sequences, s: sequence}
        round_.sealed = sealed
        return response

    def timeout(self,s):
        room=self.loading.room(s)
        if room is None or room.phase!='active' or room.started is None or time.monotonic()-room.started<300:return
        room,round_=self._current(s)
        # A terminal accepted death retains its native AA completion path.
        if round_ is not None:return
        request=play_wire.time_over()
        boxes=self._prepare(room,None,[(m,(request,))for m in room.members],())
        round_=Round(room,room.seed,completed=True,ended=room.started+300,reason='timeout')
        self.rounds[room.seed]=round_;room.phase='reporting'
        for m in room.members:m.phase='pvp_reporting'
        self._publish(boxes)

    def leave(self,s):
        room,round_=self._current(s)
        if round_ is not None and round_.sealed is not None:return round_.sealed
        now=time.monotonic()
        if round_ is not None and round_.reason=='kill' and round_.completed:
            sealed=DeathResult(room.seed,room,room.members,round_.victim,round_.killer,
                min(300,int(round_.ended-room.started)),tuple(round_.reports.items()))
            self._prepare(room,round_,(),());round_.sealed=sealed;return sealed
        elapsed=min(300,int(now-room.started))
        if elapsed<0:raise ValueError('PvP original leave clock regressed')
        other=next(m for m in room.members if m is not s)
        self._prepare(room,round_,(),())
        round_=Round(room,room.seed,completed=True,ended=now,reason='leave',leaver=s)
        round_.sealed=DeathResult(room.seed,room,room.members,s,other if elapsed>=30 else None,elapsed,(),'leave',s)
        self.rounds[room.seed]=round_;room.phase='reporting'
        for m in room.members:m.phase='pvp_reporting'
        return round_.sealed

    def result(self, s):
        room = self.loading.room(s)
        round_ = None if room is None else self.rounds.get(room.seed)
        if round_ is None or round_.sealed is None:
            return None
        for member in room.members:
            self.loading.current(member, room)
        if (round_.room is not room or round_.sealed.room is not room
                or room.phase != 'reporting' or round_.seed != room.seed):
            raise ValueError('PvP sealed result source changed')
        return round_.sealed
