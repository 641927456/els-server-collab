"""Original71B/71D/71F consent, followed by the existing225/227 town entry."""
from contextlib import closing, ExitStack
from dataclasses import dataclass
from pathlib import Path
import sqlite3, struct, time, uuid
from els_server.domain import friend_flow
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.domain.pvp_registration import _binding, _same, _envelope
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import mentor_messages as wire
from els_server.storage import mentor_relations as storage


@dataclass(eq=False)
class Consent:
    members: tuple
    bindings: tuple
    generation: str
    location: dict
    echo: bytes
    sequence: int
    payload: bytes
    expires: float


def _destination(db, actor, destination):
    from els_server.storage.seal_quests import load_character, completed_ids
    from els_server.domain.town_travel import require_destination
    character=load_character(db,actor.account.uid,actor.account.account_id)
    records={row[0]for row in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(actor.account.uid,))}
    require_destination(destination,character,completed_ids(db,actor.account.uid),records)


def authorize_entry(s,event,sequence):
    pending=getattr(s,'mentor_summon_transition',None)
    if pending is None:return False
    if (not current_lease(s) or not _same(s,pending['binding']) or not _envelope(event)
            or event.kind!=0x225 or len(event.payload)!=5 or event.payload[4]not in(0,1)
            or struct.unpack_from('>i',event.payload)[0]!=pending['destination']
            or type(sequence)is not int or not pending['sequence']<sequence<2**32
            or s.phase not in('map_loading','square_accepted') or s.dungeon_return_pending
            or s.active_map!=pending['source'] or s.account.get_location()['map']!=pending['source']):
        return False
    own=friend_flow.capture(s)
    with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
        db.execute('BEGIN');own(db);_destination(db,s,pending['destination']);own(db)
    return True


class Summons:
    def __init__(self,mentors):
        self.mentors=mentors
        self.world=mentors.world
        self.pending={}

    def _available(self,s):
        guard=self.mentors._available(s)
        if s.phase!='town_ready' or getattr(s,'mentor_summon_transition',None)is not None:
            raise storage.MentorError('Mentor summon requires an available Town actor',1979)
        return guard

    def _forget(self,pending):
        for actor in pending.members:
            if self.pending.get(actor)is pending:self.pending.pop(actor)

    def cancel(self,s):
        pending=self.pending.get(s)
        if pending is None:return
        source=pending.members[0]
        if not source.released and current_lease(source) and _same(source,pending.bindings[0]):
            # The installed world sender retires an overflowing receiver only.
            self.world.send(source,wire.summon_result(False))
        self._forget(pending)

    def expire(self):
        now=time.monotonic()
        for pending in tuple(set(self.pending.values())):
            if (now>=pending.expires or any(actor.released or not current_lease(actor)
                    or not _same(actor,binding) or actor.phase!='town_ready'
                    for actor,binding in zip(pending.members,pending.bindings))):
                self.cancel(pending.members[0])

    def invite(self,s,event,request,sequence):
        prior=self.pending.get(s)
        if prior is not None:
            if (prior.members[0]is s and prior.sequence==sequence and prior.payload==event.payload
                    and all(_same(actor,binding)for actor,binding in zip(prior.members,prior.bindings))):
                return [wire.summon_ack()]
            raise storage.MentorError('Mentor summon consent is already pending',1979)
        own=self._available(s)
        with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            db.execute('BEGIN');own(db)
            saved=storage.relation(db,s.account.uid)
            if saved is None:raise storage.MentorError('Mentor summon requires a current partner',1981)
            target=friend_flow.online(s).get(saved['partner'])
            if target is None:raise storage.MentorError('Mentor partner is offline',1979)
            if target in self.pending:raise storage.MentorError('Mentor partner has another summon',1979)
            other=self._available(target)
            if Path(target.account.store.path).resolve()!=Path(s.account.store.path).resolve():
                raise storage.MentorError('Mentor participants use different saves')
            other(db)
            location=dict(s.account.get_location())
            if request['destination']!=location['map']:
                raise storage.MentorError('Mentor summon differs from the current source map')
            # The native producer supplies its current actor coordinates,
            # like ordinary movement. Only the selected map is server-owned;
            # do not require the previous movement tick's exact float values.
            location.update(xyz=request['xyz'],board=request['board'])
            _destination(db,target,location['map'])
            notice=wire.summon_notice(location,uuid.uuid4().int)
            response=[wire.summon_ack()]
            with target.mailbox.lock:
                boxes=_prepared_boxes([(target,[notice])],response)
                own(db);other(db)
                pending=Consent((s,target),(_binding(s),_binding(target)),saved['generation'],location,
                    notice.payload,sequence,event.payload,time.monotonic()+10)
                for actor in pending.members:self.pending[actor]=pending
                for actor,box in boxes.items():actor.mailbox=box
            return response

    def answer(self,s,event,request,sequence):
        pending=self.pending.get(s)
        if pending is None:
            return [wire.summon_error(1977)]if request['accepted']else []
        source,target=pending.members
        if (target is not s or request['echo']!=pending.echo
                or any(not _same(actor,binding)for actor,binding in zip(pending.members,pending.bindings))):
            raise storage.MentorError('Mentor summon consent does not match its origin')
        if not request['accepted']:
            self.cancel(s)
            return []
        guards=[self._available(actor)for actor in pending.members]
        with ExitStack()as locks,closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            db.execute('BEGIN')
            for guard in guards:guard(db)
            saved=storage.relation(db,source.account.uid)
            if (saved is None or saved['partner']!=s.account.uid or saved['generation']!=pending.generation
                    or source.active_map!=pending.location['map']):
                raise storage.MentorError('Mentor summon relation or destination retired',1981)
            _destination(db,s,pending.location['map'])
            response=[wire.summoned(pending.location)]
            locks.enter_context(source.mailbox.lock)
            boxes=_prepared_boxes([(source,[wire.summon_result(True)])],response)
            for guard in guards:guard(db)
            self._forget(pending)
            s.mentor_summon_transition=dict(binding=_binding(s),destination=pending.location['map'],
                source=s.active_map,sequence=sequence,generation=pending.generation)
            s.phase='map_loading';s.pending_map=None;s.inventory_town_sync_sent=False
            self.world.leave(s)
            for actor,box in boxes.items():actor.mailbox=box
            return response

    def entry(self,s,event,sequence):
        pending=getattr(s,'mentor_summon_transition',None)
        if pending is None:return None
        if event.kind==0x225:
            try:allowed=authorize_entry(s,event,sequence)
            except(ValueError,sqlite3.Error):allowed=False
            if not allowed:return [wire.message(0x226,struct.pack('>5i',515,0,0,0,0))]
        elif event.kind==0x227:
            if (not _same(s,pending['binding']) or s.pending_map!=pending['destination']
                    or s.phase not in('square_accepted','town_ready')):
                return [wire.message(0x228,struct.pack('>i',515))]
        return None
