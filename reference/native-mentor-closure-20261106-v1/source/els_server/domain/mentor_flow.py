"""Native mentor consent and online projection, under the existing world worker."""
from contextlib import closing,ExitStack
from dataclasses import dataclass
from pathlib import Path
import sqlite3,time,uuid
from els_server.domain import friend_flow,pvp_actor
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.domain.pvp_registration import _binding,_same,_envelope
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import mentor_messages as wire
from els_server.storage import mentor_relations as storage


@dataclass(eq=False)
class Invitation:
    members: tuple
    bindings: tuple
    teacher: int
    student: int
    generation: str
    expires: float


class Mentors:
    def __init__(self,world):
        self.world=world
        self.pending={}
        from els_server.domain.mentor_summon import Summons
        self.summons=Summons(self)

    def _available(self,s):
        own=friend_flow.capture(s)
        actor=pvp_actor.capture(self.world,s)
        if (not s.enter_town or s.phase not in ('town_ready','guild_agit_ready')
                or s.dungeon_return_pending or self.world.pvp.room(s)is not None
                or self.world.dungeons.transport_room(s)is not None
                or s in self.world.player_trades.by_session
                or s in self.world.pvp.registrations.queue or s in self.world.pvp.registrations.offers
                or getattr(s,'town_warp_transition',None)is not None):
            raise storage.MentorError('Mentor requires an available Town/GuildAgit actor',1978)
        if s.phase=='town_ready':
            location=s.account.get_location();key=(1,location['map'])
            if (s.active_map!=location['map'] or s.pending_map!=location['map']
                    or not {0x225,0x227}.issubset(s.completed)
                    or self.world.members.get(s)!=key or s not in self.world.towns.get(key,{})):
                raise storage.MentorError('Mentor actor has not completed Town admission',1978)
            guild=None
        else:
            from els_server.domain.guild_agit_flow import bank_capture
            _,guild=bank_capture(s)
        def guard(db):
            own(db);actor()
            if guild is not None:guild(db)
        return guard

    def _forget(self,invitation):
        for member in invitation.members:
            if self.pending.get(member)is invitation:self.pending.pop(member)

    def _decline(self,invitation,reason):
        inviter,recipient=invitation.members
        if (not inviter.released and current_lease(inviter)
                and _same(inviter,invitation.bindings[0])):
            guard=pvp_actor.safe_capture(self.world,inviter)
            if guard is None:
                self._forget(invitation)
                return
            with inviter.mailbox.lock:
                boxes=_prepared_boxes([(inviter,[wire.declined(recipient.account.uid,reason)])],[])
                guard()
                self._forget(invitation)
                for peer,box in boxes.items():peer.mailbox=box
        else:
            self._forget(invitation)

    def expire(self):
        self.summons.expire()
        now=time.monotonic()
        for invitation in tuple(set(self.pending.values())):
            if now>=invitation.expires:self._decline(invitation,1960)

    def _invite(self,s,request):
        target=friend_flow.online(s).get(request['target'])
        if target is None or target is s:
            raise storage.MentorError('Mentor target is not online')
        if any(peer in self.pending for peer in(s,target)):
            raise storage.MentorError('Mentor invitation already pending',1978)
        if Path(s.account.store.path).resolve()!=Path(target.account.store.path).resolve():
            raise storage.MentorError('Mentor participants use different saves')
        guards=[self._available(peer)for peer in(s,target)]
        with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            db.execute('BEGIN')
            for guard in guards:guard(db)
            mine=storage.role(db,s.account.uid,s.account.account_id)
            if mine==2:raise storage.MentorError('Mentor qualification is incomplete',1957)
            teacher,student=(s,target)if mine==0 else(target,s)
            storage.require_pair_eligibility(db,teacher.account.uid,student.account.uid)
            row=storage.public_info(db,s.account.uid,s,is_student=mine==1)
            response=[wire.acknowledgement(0x1e8,text=target.account.character_identity()['name'])]
            with target.mailbox.lock:
                boxes=_prepared_boxes([(target,[wire.invitation(row)])],response)
                for guard in guards:guard(db)
                invitation=Invitation((s,target),(_binding(s),_binding(target)),teacher.account.uid,
                    student.account.uid,str(uuid.uuid4()),time.monotonic()+10)
                for peer in invitation.members:self.pending[peer]=invitation
                for peer,box in boxes.items():peer.mailbox=box
            return response

    def _answer(self,s,event,request,operation):
        invitation=self.pending.get(s)
        if invitation is not None:
            inviter,recipient=invitation.members
            if (recipient is not s or request['target']!=inviter.account.uid
                    or any(not _same(peer,binding)for peer,binding in zip(invitation.members,invitation.bindings))):
                raise storage.MentorError('Mentor consent does not match its original participants')
            if not request['accepted']:
                if request['reason']not in(1960,1964,1979):
                    raise storage.MentorError('Unknown original mentor refusal')
                self._decline(invitation,request['reason'])
                return []
        elif not request['accepted']:
            # A native10s popup can return its timeout after the server expired it.
            return []
        actors=()if invitation is None else invitation.members
        guards=[self._available(peer)for peer in actors]
        own=friend_flow.capture(s)
        def guard(db):
            own(db)
            for check in guards:check(db)
            if invitation is not None and any(self.pending.get(peer)is not invitation for peer in actors):
                raise storage.MentorError('Mentor consent generation retired')
        boxes={}
        with ExitStack()as locks:
            def encode(db,result,repeated):
                nonlocal boxes
                saved=storage.relation(db,s.account.uid)
                if saved is None or request['target']!=saved['partner']:
                    raise storage.MentorError('Mentor answer no longer names this partner')
                present=friend_flow.online(s)
                response=[wire.answer(saved['partner'],storage.public_info(db,saved['partner'],
                    present.get(saved['partner']),saved=saved),True)]
                deliveries=[]
                if not repeated:
                    other=next(peer for peer in actors if peer is not s)
                    other_saved=storage.relation(db,other.account.uid)
                    deliveries=[(other,[wire.answer(s.account.uid,storage.public_info(db,s.account.uid,s,
                        saved=other_saved),True)])]
                for peer,_ in sorted(deliveries,key=lambda entry:entry[0].account.uid):locks.enter_context(peer.mailbox.lock)
                boxes=_prepared_boxes(deliveries,response)
                return response
            plan=None if invitation is None else dict(teacher=invitation.teacher,student=invitation.student,
                recipient=s.account.uid,generation=invitation.generation)
            response=storage.perform(s.account.store.path,s.account.uid,s.account.account_id,0x1eb,
                event.payload,operation,guard,encode,invitation=plan)
            if invitation is not None:self._forget(invitation)
            for peer,box in boxes.items():peer.mailbox=box
        return response

    def _remove(self,s,event,request,operation):
        own=friend_flow.capture(s)
        guards=[];boxes={}
        with ExitStack()as locks:
            def guard(db):
                own(db)
                for check in guards:check(db)
            def encode(db,result,repeated):
                nonlocal boxes
                response=[wire.acknowledgement(0x1e4),wire.removed(request['target'],'师徒关系已解除。')]
                deliveries=[]
                peer=friend_flow.online(s).get(request['target'])
                if peer is not None and not repeated:
                    guards.append(friend_flow.capture(peer))
                    deliveries=[(peer,[wire.removed(s.account.uid,'师徒关系已解除。')])]
                    locks.enter_context(peer.mailbox.lock)
                boxes=_prepared_boxes(deliveries,response)
                return response
            response=storage.perform(s.account.store.path,s.account.uid,s.account.account_id,0x1e4,
                event.payload,operation,guard,encode)
            for peer,box in boxes.items():peer.mailbox=box
        self.summons.cancel(s)
        return response

    def _search(self,s,operation):
        own=self._available(s)
        if s.phase!='town_ready':raise storage.MentorError('Native mentor search requires Town state14',1958)
        present=friend_flow.online(s);guards=[];boxes={}
        with ExitStack()as locks:
            def guard(db):
                own(db)
                for check in guards:check(db)
            def encode(db,result,repeated):
                nonlocal boxes
                response=[wire.acknowledgement(0x714)]
                deliveries=[]
                if not repeated:
                    notice=wire.search_notice(storage.character(db,uid=s.account.uid))
                    for peer in sorted(present.values(),key=lambda actor:actor.account.uid):
                        guards.append(friend_flow.capture(peer));locks.enter_context(peer.mailbox.lock)
                        deliveries.append((peer,[notice]))
                boxes=_prepared_boxes(deliveries,response)
                return response
            response=storage.search(s.account.store.path,s.account.uid,s.account.account_id,operation,guard,encode)
            for peer,box in boxes.items():peer.mailbox=box
        return response

    def request(self,s,event,sequence):
        if event.event_id==0x202:
            entry=self.summons.entry(s,event,sequence)
            if entry is not None:return entry
        if event.event_id!=0x202 or event.kind not in wire.REQUESTS:return None
        account=s.account;uid=account.uid
        self.expire()
        try:
            friend_flow.selected(s)
            if not _envelope(event) or type(sequence)is not int or not 1<=sequence<2**32:
                raise storage.MentorError('Mentor request envelope')
            parsed=wire.request(event.kind,event.payload)
            operation=s.shop_session_id+':mentor:'+str(uid)+':'+str(sequence)
            if event.kind==0x1e8:return self._invite(s,parsed)
            if event.kind==0x1eb:return self._answer(s,event,parsed,operation)
            if event.kind==0x1e4:return self._remove(s,event,parsed,operation)
            if event.kind==0x714:return self._search(s,operation)
            if event.kind==0x71b:return self.summons.invite(s,event,parsed,sequence)
            if event.kind==0x71f:return self.summons.answer(s,event,parsed,sequence)
        except(ValueError,sqlite3.Error,UnicodeError,OverflowError)as error:
            if s.account is not account or s.account.uid!=uid or not current_lease(s):return []
            code=getattr(error,'code',1977)
            if event.kind==0x1eb:return [wire.declined(0,code)]
            if event.kind==0x71b:return [wire.summon_ack(code)]
            if event.kind==0x71f:return [wire.summon_error(code)]
            return [wire.acknowledgement(event.kind,result=code)]

    def synchronize(self,s,event,response,*,force=False,publish_own=False):
        if event is not None and event.kind==0x227 and s.phase=='town_ready':
            s.mentor_summon_transition=None
        cold=any(message.event_id==0x201 and message.kind==0x2f for message in response)
        if not force and not cold and event.kind not in(0x28,0x225,0x227,0x219,0x80f,0xf4,0x1e4,0x1eb):
            return response
        if not current_lease(s) or s.phase in('closing','channels_ready'):
            return response
        own=friend_flow.capture(s)
        present=friend_flow.online(s)
        with ExitStack()as locks,closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            db.execute('BEGIN');own(db)
            saved=storage.relation(db,s.account.uid)
            role=storage.role(db,s.account.uid,s.account.account_id)
            row=storage.character(db,uid=s.account.uid)
            signature=(s.account.uid,role,row['level'],row['unit_class'],saved)
            previous=getattr(s,'mentor_presence_signature',None)
            if not cold and signature==previous:return response
            answer=list(response)+[wire.role(role)]
            if saved is not None:
                partner=storage.public_info(db,saved['partner'],present.get(saved['partner']),saved=saved)
                answer.append(wire.partner(partner))
            elif previous is not None and previous[4]is not None and not any(
                    message.event_id==0x201 and message.kind==0x1e6 for message in answer):
                answer.append(wire.removed(previous[4]['partner'],'师徒关系已解除。'))
            deliveries=[];guards=[]
            if saved is not None:
                peer=present.get(saved['partner'])
                if peer is not None:
                    guards.append(friend_flow.capture(peer))
                    deliveries.append((peer,[wire.partner(storage.public_info(db,s.account.uid,s,saved=saved),notify=cold)]))
            if publish_own:deliveries.append((s,answer))
            for peer,_ in sorted(deliveries,key=lambda entry:entry[0].account.uid):locks.enter_context(peer.mailbox.lock)
            boxes=_prepared_boxes(deliveries,[]if publish_own else answer)
            own(db)
            for guard in guards:guard(db)
            s.mentor_presence_signature=signature
            for peer,box in boxes.items():peer.mailbox=box
            return []if publish_own else answer

    def disconnect(self,s):
        self.summons.cancel(s)
        invitation=self.pending.get(s)
        if invitation is not None:self._decline(invitation,1960)
        previous=getattr(s,'mentor_presence_signature',None)
        if previous is None:return
        owner=previous[0]
        replacement=s.application.playing.get(s.account.account_id)
        if replacement is not None and replacement is not s and replacement.account.uid==owner:return
        present=friend_flow.online(s);present.pop(owner,None)
        with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            db.execute('BEGIN')
            storage.require_owner(db,owner,s.identity['id'])
            saved=storage.relation(db,owner)
            peer=None if saved is None else present.get(saved['partner'])
            if peer is not None:
                guard=friend_flow.capture(peer)
                with peer.mailbox.lock:
                    boxes=_prepared_boxes([(peer,[wire.partner(storage.public_info(db,owner,None,saved=saved))])],[])
                    guard(db)
                    for actor,box in boxes.items():actor.mailbox=box
        s.mentor_presence_signature=None

    def reconcile(self,application):
        for peer in tuple(application.playing.values()):
            if current_lease(peer) and 0x28 in peer.completed:
                self.synchronize(peer,None,[],force=True,publish_own=True)
