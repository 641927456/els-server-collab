"""Serialized real-player pet matching, loading and server-owned turns.

Random matches and invited lobbies share prepared admission and server-owned
turns. No XP, ED, AP or ranking writer is called here.
"""
from copy import copy
from contextlib import closing
from pathlib import Path
from dataclasses import dataclass,field,replace
import sqlite3,struct,time,uuid
from els_server.domain import pvp_actor
from els_server.domain.pvp_registration import _binding,_same,_envelope
from els_server.domain.pvp_loading import _inventory_signature
from els_server.domain.party_commands import _prepared_boxes
from els_server.domain.pet_battle import Match,Action
from els_server.domain.pet_battle_projection import notice
from els_server.domain.pet_battle_scene import spawn as scene_spawn
from els_server.domain.summons import summon_ack
from els_server.storage.pet_battle_roster import roster
from els_server.storage.read_scope import snapshot_connection
from els_server.protocol import pet_battle_messages as pet_wire
from els_server.protocol import pet_battle_room_messages as room_wire
from els_server.protocol import pvp_match_messages as queue_wire
from els_server.protocol import pvp_play_messages as play_wire
from els_server.protocol import pvp_loading_messages as loading_wire
from els_server.protocol import dungeon_messages,social_messages
from els_server.protocol.protocol_codec import Event

SELECT_SECONDS=15
# Native emits its final partial plan after its own15-second window. Delivery
# allowance must be qualified with the actual bridge before this is released.
DELIVERY_SECONDS=2


@dataclass(frozen=True)
class Ticket:
    session:object
    binding:tuple
    selection:tuple


@dataclass(eq=False)
class Offer:
    identity:int
    seed:str
    tickets:tuple
    confirmed:frozenset=frozenset()


@dataclass(eq=False)
class Room:
    identity:int
    seed:str
    members:tuple
    tickets:tuple
    entrants:dict
    users:dict
    slots:tuple
    engine:Match
    phase:str='loading'
    progress:dict=field(default_factory=dict)
    animation_done:frozenset=frozenset()
    requests:dict=field(default_factory=dict)
    deadline:float=0
    scene:object=None
    scene_sent:bool=False
    mode:str='random'

    def user(self,owner,pet_vector):
        before,after=self.users[owner]
        return before+pet_vector+after


def _clone(engine):
    # Production matches use stateless SystemRandom. Only the candidate's
    # domain state changes before packet allocation/publication succeeds.
    candidate=copy(engine)
    candidate.sides=tuple(replace(s,pets={uid:replace(p)for uid,p in s.pets.items()})for s in engine.sides)
    candidate._owners={s.uid:s for s in candidate.sides}
    return candidate


class PetBattles:
    def __init__(self,world):
        self.world=world;self.queue={};self.offers={};self.rooms={}
        self.invitations={};self.lobbies={}

    def room(self,s):return self.rooms.get(s)

    def busy(self,s):return any(s in table for table in(self.queue,self.offers,self.rooms,self.invitations,self.lobbies))

    def town(self,s):
        pvp_actor.actor(self.world,s)
        w=self.world;pvp=w.pvp
        location=s.account.get_location();map_id=location['map']
        if (s.phase!='town_ready' or not s.enter_town or s.dungeon_return_pending
                or s.active_map!=map_id or s.pending_map!=map_id
                or w.members.get(s)!=(1,map_id) or s not in w.towns.get((1,map_id),{})
                or s in w.party_of or w.dungeons.transport_room(s)is not None
                or pvp.room(s)is not None or w.racing.room(s)is not None
                or s in pvp.registrations.queue or s in pvp.registrations.offers
                or s in pvp.duels.pending):
            raise ValueError('Pet battle current solo town actor required')

    def cold(self,ticket):
        s=ticket.session
        if not _same(s,ticket.binding):raise ValueError('Pet battle retired registration actor')
        with snapshot_connection(s.account.store.path)as db:
            db.execute('BEGIN')
            return roster(db,s.account.uid,s.account.account_id,ticket.selection)

    def current(self,s,room):
        if self.rooms.get(s)is not room or s not in room.members:
            raise ValueError('Pet battle current room required')
        ticket=next(t for t in room.tickets if t.session is s)
        pvp_actor.actor(self.world,s)
        if (not _same(s,ticket.binding) or s.phase!='pet_'+room.phase
                or s.active_map!=room_wire.WORLD or s.pending_map!=room_wire.WORLD
                or s in self.world.members or s in self.world.party_of):
            raise ValueError('Pet battle original actor/phase changed')

    def prepare(self,members,deliveries,responses=()):
        guards=tuple(pvp_actor.capture(self.world,s)for s in members)
        boxes=_prepared_boxes(deliveries,responses)
        for guard in guards:guard()
        return boxes

    @staticmethod
    def publish(boxes):
        for s,box in boxes.items():s.mailbox=box

    def register(self,s,event):
        self.town(s)
        if s in self.invitations or s in self.lobbies:raise ValueError('Pet invited lobby owns current registration')
        hint,selection=pet_wire.selection(event.payload)
        ticket=Ticket(s,_binding(s),selection);self.cold(ticket)
        if s in self.offers:raise ValueError('Pet battle already offered')
        if s in self.queue and self.queue[s].selection!=selection:
            raise ValueError('Pet battle queued configuration cannot change')
        replies=[queue_wire.registration_ack(0,False,''),queue_wire.wait_notification(0,((13,0,False),))]
        self.prepare((s,),(),replies);self.town(s);self.cold(ticket)
        self.queue[s]=ticket
        self.match()
        return replies

    def match(self):
        for s,ticket in tuple(self.queue.items()):
            try:self.town(s);self.cold(ticket)
            except (ValueError,sqlite3.Error):
                if self.queue.get(s)is ticket:self.queue.pop(s)
        tickets=tuple(self.queue.values())
        for index,a in enumerate(tickets):
            for b in tickets[index+1:]:
                if a.session.account.account_id==b.session.account.account_id:continue
                for t in(a,b):self.town(t.session);self.cold(t)
                generation=uuid.uuid4();identity=generation.int&((1<<63)-1)
                if not identity:continue
                offer=Offer(identity,str(generation),(a,b))
                event=play_wire.matched(identity);members=(a.session,b.session)
                boxes=self.prepare(members,[(s,(event,))for s in members])
                for t in(a,b):
                    if self.queue.get(t.session)is not t:raise ValueError('Pet battle queue changed')
                    self.town(t.session);self.cold(t)
                for s in members:self.queue.pop(s);self.offers[s]=offer
                self.publish(boxes);return

    def confirm(self,s,event):
        offer=self.offers[s];members=tuple(t.session for t in offer.tickets)
        flags,excluded,tail=queue_wire.confirmation(event.payload)
        if flags!=(True,True,False)or tail:raise ValueError('Pet battle native confirmation')
        for t in offer.tickets:
            if self.offers.get(t.session)is not offer:raise ValueError('Pet battle retired offer')
            self.town(t.session);self.cold(t)
        confirmed=offer.confirmed|{s}
        if len(confirmed)!=2:offer.confirmed=confirmed;return []
        return self.admit(s,offer)

    def admit(self,s,offer,*,mode='random',guard=None,replies=()):
        members=tuple(t.session for t in offer.tickets)
        if guard is not None:guard()
        entrants={t.session.account.uid:self.cold(t)for t in offer.tickets}
        towns=(tuple(self.world.members.items()),tuple((k,id(v),tuple(v.items()))for k,v in self.world.towns.items()))
        engine=Match(tuple((uid,tuple(e.fact for e in pets))for uid,pets in entrants.items()))
        users={};slots=[];full=[]
        signatures=tuple(_inventory_signature(m)for m in members)
        for index,m in enumerate(members):
            captured={}
            def capture(body,spans):captured.update(body=body,spans=spans)
            body=dungeon_messages.member(m.account.get_skills(),m.account.character(),
                m.account.get_inventory_snapshot()['items'],account_id=m.account.account_id,
                peer_port=21100+index,capture=capture)
            offset,size=captured['spans']['0x5ec'];users[m.account.uid]=(body[:offset],body[offset+size:])
        room=Room(offer.identity,offer.seed,members,offer.tickets,entrants,users,(),engine,mode=mode)
        for index,m in enumerate(members):
            side=engine.sides[index]
            vector=struct.pack('>I',3)+b''.join(e.record+struct.pack('>iii',side.pets[e.fact.uid].ability,100,0)for e in entrants[m.account.uid])
            body=room.user(m.account.uid,vector);full.append((m.account.uid,body))
            slots.append(bytes((index,4,int(index==0),1,0,0))+struct.pack('>iI',index,1)+body+bytes(8))
        room.slots=tuple(slots)
        admission=room_wire.admission(full,room.identity,s.port_probe_port)
        deliveries=[(m,(admission,))for m in members]
        for key in{self.world.members[m]for m in members}:
            removed=[m.account.uid for m in members if self.world.members[m]==key]
            event=social_messages.town_members(removed=removed)
            deliveries.extend((peer,(event,))for peer in self.world.towns[key]if peer not in members)
        boxes=self.prepare(tuple({p for p,events in deliveries}),deliveries)
        if tuple(_inventory_signature(m)for m in members)!=signatures:raise ValueError('Pet battle member inputs changed')
        if towns!=(tuple(self.world.members.items()),tuple((k,id(v),tuple(v.items()))for k,v in self.world.towns.items())):
            raise ValueError('Pet battle old town membership changed')
        for t in offer.tickets:
            self.town(t.session)
            if self.cold(t)!=entrants[t.session.account.uid]or guard is None and self.offers.get(t.session)is not offer:
                raise ValueError('Pet battle late roster/offer changed')
        if guard is not None:guard()
        for m in members:
            key=self.world.members.pop(m);self.world.towns[key].pop(m)
            if not self.world.towns[key]:self.world.towns.pop(key)
            self.offers.pop(m,None);self.rooms[m]=room;m.phase='pet_loading'
            m.active_map=m.pending_map=room_wire.WORLD
        self.publish(boxes);return list(replies)

    def loaded(self,s,event,room):
        value=loading_wire.progress_request(event.payload)
        if room.phase!='loading':
            if value==100 and room.progress.get(s)==100:return[loading_wire.progress_ack(100)]
            raise ValueError('Pet battle loading phase')
        if value<room.progress.get(s,0):raise ValueError('Pet battle regressing load')
        progress={**room.progress,s:value};replies=[loading_wire.progress_ack(value)]
        events=[loading_wire.progress_notice(s.account.uid,value)]
        start=all(progress.get(m)==100 for m in room.members)
        if start:
            events.append(loading_wire.play_start(room.slots))
            if room.scene is not None:events.append(room.scene)
            events.append(notice(room.engine,room.entrants,room.user))
        boxes=self.prepare(room.members,[(m,tuple(events))for m in room.members],replies)
        for m in room.members:self.current(m,room)
        room.progress=progress
        if start:
            room.scene_sent=room.scene is not None
            room.phase='selecting';room.deadline=time.monotonic()+SELECT_SECONDS+DELIVERY_SECONDS
            for m in room.members:m.phase='pet_selecting'
        self.publish(boxes);return replies

    def scene_actors(self,s,event,room):
        if (s is not room.members[0] or room.phase not in('loading','selecting','animating')
                or room.engine.number!=1 and room.scene is None):
            raise ValueError('Pet scene original host/start required')
        scene=scene_spawn(event.payload);replies=[summon_ack()]
        if room.scene is not None:
            if room.scene.payload!=scene.payload:raise ValueError('Pet scene source changed')
            self.prepare((s,),(),replies);return replies
        publish=room.phase!='loading'
        deliveries=[(m,(scene,))for m in room.members]if publish else[]
        boxes=self.prepare(room.members,deliveries,replies)
        for m in room.members:self.current(m,room)
        room.scene=scene;room.scene_sent=publish
        self.publish(boxes);return replies

    def commands(self,s,event,room):
        previous=room.requests.get(s)
        if previous is not None:
            if previous!=event.payload:raise ValueError('Pet battle completed selection cannot change')
            replies=[pet_wire.action_ack(0)];self.prepare((s,),(),replies)
            return replies
        pairs,active=pet_wire.actions(event.payload)
        candidate=_clone(room.engine)
        side=candidate._side(s.account.uid)
        # 300D510 resets UI+70 to0. 3008DC0 sends that field separately
        # from the active member: zero retains the living current pet.
        if active==0:active=side.active if side.pets[side.active].hp>0 else None
        actions=tuple(Action(kind,target)if kind else None for kind,target in pairs)
        if any(a is None for a in actions):
            if time.monotonic()<room.deadline-DELIVERY_SECONDS:raise ValueError('Pet battle early incomplete plan')
            if side.actions is not None:raise ValueError('Pet battle changed completed plan')
            selected,plan=candidate._plan(side,actions,active,fill=True)
            candidate.submit(s.account.uid,plan,selected)
        else:candidate.submit(s.account.uid,actions,active)
        replies=self.commit_turn(room,candidate,[pet_wire.action_ack(0)])
        room.requests[s]=bytes(event.payload)
        return replies

    def commit_turn(self,room,candidate,replies=(),*,result=None,previous=None):
        if candidate.phase=='selecting'and all(s.actions is not None for s in candidate.sides):
            previous=candidate.snapshot();result=candidate.resolve()
        events=()if result is None else(notice(candidate,room.entrants,room.user,result=result,previous=previous),)
        boxes=self.prepare(room.members,[(m,events)for m in room.members]if events else(),replies)
        for m in room.members:self.current(m,room)
        room.engine=candidate
        if result is not None:
            room.phase='animating';room.animation_done=frozenset()
            for m in room.members:m.phase='pet_animating'
        self.publish(boxes);return list(replies)

    def sealed_result(self,room,candidate,event):
        from els_server.storage.item_actor import require_active_character
        from els_server.storage.profession_state import require_owner
        from els_server.storage.pet_battle_results import seal
        from els_server.storage.pet_battle_quest_scope import record
        guards=tuple(pvp_actor.capture(self.world,m)for m in room.members)
        path=room.members[0].account.store.path
        if any(Path(m.account.store.path).resolve()!=Path(path).resolve()for m in room.members):
            raise ValueError('Pet result requires the original shared store')
        def guard(db):
            for captured in guards:captured()
            for m in room.members:
                self.current(m,room);require_active_character(db,m.account.uid)
                require_owner(db,m.account.uid,m.account.account_id)
        winner=next(m for m in room.members if m.account.uid==candidate.winner)
        fact=dict(mode=room.mode,winner=candidate.winner,round=candidate.number,
            participants=[dict(uid=m.account.uid,account=m.account.account_id,
                pets=[dict(uid=p.uid,hp=p.hp,ability=p.ability,points=p.points,attribute=p.attribute)
                    for p in candidate._side(m.account.uid).pets.values()])for m in room.members])
        now=int(time.time())
        with closing(sqlite3.connect(path))as db,db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            guard(db);seal(db,room.seed,candidate.winner,winner.account.account_id,now,fact,guard)
            progress=record(db,winner.account.uid,winner.account.account_id,room.seed,guard,now)if room.mode=='random'else[]
            boxes=self.prepare(room.members,[(m,(event,*progress)if m is winner else(event,))for m in room.members])
            guard(db)
        return boxes

    def animation(self,s,event,room):
        if event.payload:raise ValueError('Pet battle animation ACK body')
        if room.phase!='animating':return []
        done=room.animation_done|{s}
        if len(done)!=2:room.animation_done=done;return []
        candidate=_clone(room.engine);candidate.finish_animation()
        finished=candidate.phase=='finished'
        event=(Event(0x201,kind=0xa6f,payload=struct.pack('>?BQi',False,0,candidate.winner,0))
            if finished else notice(candidate,room.entrants,room.user))
        if finished:boxes=self.sealed_result(room,candidate,event)
        else:
            boxes=self.prepare(room.members,[(m,(event,))for m in room.members])
            for m in room.members:self.current(m,room)
        room.engine=candidate;room.animation_done=done
        room.phase='result'if finished else'selecting'
        if not finished:room.requests={}
        room.deadline=0 if finished else time.monotonic()+SELECT_SECONDS+DELIVERY_SECONDS
        for m in room.members:m.phase='pet_'+room.phase
        self.publish(boxes);return []

    def exit(self,s,event,room):
        if event.payload or room.phase!='result':raise ValueError('Pet battle normal result exit')
        from els_server.domain import pet_battle_lobby as lobby
        replies=[Event(0x201,kind=0x111,payload=bytes(12)),s.saved_user_sync()]
        self.prepare((s,),(),replies);self.current(s,room)
        self.rooms.pop(s);s.phase='map_loading';s.pending_map=None
        s.dungeon_return_pending=True;s.inventory_town_sync_sent=True
        lobby.returned(self,s,room)
        return replies

    def request(self,s,event,sequence):
        if event.event_id!=0x202:return None
        from els_server.domain.pet_battle_lobby import handle as lobby_handle
        reply=lobby_handle(self,s,event,sequence)
        if reply is not None:return reply
        kind=event.kind;room=self.room(s)
        own_registration=kind==0x342 and event.payload[:5]==b'\0\0\0\1\x0d'
        handled=own_registration or kind==0x345 and(s in self.queue or s in self.offers)or kind==0x34a and s in self.offers or room is not None and kind in(0x91,0xa6c,0xa6e,0x110,0x2ce,0x34a)
        if not handled:return None
        if not _envelope(event):return []
        try:
            if own_registration:return self.register(s,event)
            if kind==0x345:
                self.town(s)
                if s in self.offers:raise ValueError('Pet old queue cancellation after offer')
                if queue_wire.cancellation(event.payload)!=0:raise ValueError('Pet battle self cancellation')
                replies=[queue_wire.cancellation_ack(0,False,0)];self.prepare((s,),(),replies)
                self.queue.pop(s);return replies
            if kind==0x34a and s in self.offers:return self.confirm(s,event)
            self.current(s,room)
            if kind==0x34a:
                flags,excluded,tail=queue_wire.confirmation(event.payload)
                if flags!=(True,True,False)or tail:raise ValueError('Pet battle repeated native confirmation')
                self.prepare((s,),(),());self.current(s,room)
                return []
            if kind==0x91:return self.loaded(s,event,room)
            if kind==0x2ce:return self.scene_actors(s,event,room)
            if kind==0xa6c:return self.commands(s,event,room)
            if kind==0xa6e:return self.animation(s,event,room)
            if kind==0x110:return self.exit(s,event,room)
        except (ValueError,sqlite3.Error):
            guard=pvp_actor.safe_capture(self.world,s)
            replies=([queue_wire.registration_ack(-1,False,'')]if own_registration else
                [queue_wire.cancellation_ack(-1,False,0)]if kind==0x345 else
                [summon_ack(-1)]if kind==0x2ce else
                [pet_wire.action_ack(-1)]if kind==0xa6c else
                [loading_wire.progress_ack(0,-1)]if kind==0x91 else[])
            return pvp_actor.failed(guard,lambda:replies)

    def periodic(self,s):
        from els_server.domain.pet_battle_lobby import periodic as lobby_periodic
        lobby_periodic(self,s)
        room=self.room(s)
        if room is not None and room.phase=='selecting'and time.monotonic()>=room.deadline:
            for m in room.members:self.current(m,room)
            candidate=_clone(room.engine);previous=candidate.snapshot();result=candidate.timeout()
            self.commit_turn(room,candidate,result=result,previous=previous)

    def disconnect(self,s):
        from els_server.domain.pet_battle_lobby import disconnect as lobby_disconnect
        lobby_disconnect(self,s)
        self.queue.pop(s,None);offer=self.offers.pop(s,None)
        if offer is not None:
            for t in offer.tickets:
                self.offers.pop(t.session,None)
                if t.session is not s and not t.session.released:t.session.coop_error='宠物对战对手已离线，请重新匹配。'
        room=self.rooms.pop(s,None)
        if room is not None and room.phase!='result':
            for other in room.members:
                self.rooms.pop(other,None)
                if other is not s and not other.released:other.coop_error='宠物对战连接中断，本场不计胜负。'

    def manifest(self,app,account):
        s=app.playing.get(account);room=self.room(s)
        if room is None or s.application is not app:return None
        for m in room.members:
            if self.room(m)is room:self.current(m,room)
        return dict(epoch=room.seed,uid=s.account.uid,peers=[dict(uid=m.account.uid,port=21100+i)for i,m in enumerate(room.members)if self.room(m)is room])

    def relay_target(self,app,account,epoch,target):
        manifest=self.manifest(app,account)
        if manifest is None or manifest['epoch']!=epoch:return None
        s=app.playing[account];room=self.room(s)
        other=next((m for m in room.members if m is not s and self.room(m)is room and m.account.uid==target),None)
        return None if other is None else(other.account.account_id,s.account.uid)

    def relay_lost(self,s):
        room=self.room(s)
        if room is not None and room.phase!='result':self.disconnect(s)
