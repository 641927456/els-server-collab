"""Real3–6-player racing, native room loading and durable server outcomes."""
from contextlib import closing
from dataclasses import dataclass,field
from pathlib import Path
import math,sqlite3,struct,time,uuid
from els_server.domain import pvp_actor
from els_server.domain.pvp_registration import _binding,_same,_envelope
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import social_messages as social,mount_racing_messages as wire,pvp_loading_messages as loading
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage import mount_races


@dataclass(eq=False)
class Room:
    identity:int
    seed:str
    members:tuple
    bindings:tuple
    mounts:dict
    slots:tuple
    participants:tuple
    party:object=None
    phase:str='loading'
    progress:dict=field(default_factory=dict)
    started:float|None=None
    data:dict|None=None


@dataclass(eq=False)
class Offer:
    identity:int
    members:tuple
    bindings:tuple
    accepted:set=field(default_factory=set)
    deadline:float=0.


def ack(kind,result=0):
    return Event(0x201,kind=kind,payload=struct.pack('>i',(21) if result == -1 else result))


class FriendsRacing:
    def __init__(self,world):
        self.world=world;self.rooms={};self.queue={};self.offers={};self.gates={};self.invitations={}
        self.partial_since=None;self.next_identity=970001

    def room(self,s):return self.rooms.get(s)

    @staticmethod
    def publish(boxes):
        for s,box in boxes.items():s.mailbox=box

    def town(self,s):
        pvp_actor.actor(self.world,s)
        party=self.world.party_of.get(s)
        if(s.phase!='town_ready' or not s.enter_town or not {0x225,0x227}<=s.completed
           or s.dungeon_return_pending or s.active_map!=s.account.get_location()['map']
           or self.world.members.get(s)!=(1,s.active_map) or s.account.character()['level']<99
           or self.world.dungeons.transport_room(s)is not None or self.world.pvp.room(s)is not None
           or self.world.pet_battles.busy(s)
           or s in self.world.pvp.registrations.queue or s in self.world.pvp.registrations.offers
           or party and any(party.get(k)for k in('raid_party','recruitment','solo_challenge','challenge','challenge_pending'))):
            raise ValueError('Racing current99-level noncombat actor required')

    def mount(self,s):
        self.town(s);saved=getattr(s,'racing_selected_mount',None)
        if not getattr(s,'racing_mode',False)or saved is None:raise ValueError('Select a permanent racing mount')
        from els_server.domain.tenebros_capacity_flow import selected
        path,owner,account,prepare=selected(s)
        return mount_races.selected(path,owner,account,saved['uid'],prepare=prepare)

    def notices(self,party,*,reset=False):
        group=([social.party_removed()]if reset else[])+[social.party_snapshot(party),Event(0x201,kind=0x147,payload=struct.pack('>iBB',150060,0,0))]
        for m in party['members']:
            selected=getattr(m,'racing_selected_mount',None)
            if selected is not None:group.append(wire.member_mount(m.account.uid,selected,getattr(m,'racing_mode',False)))
        return group

    def selection(self,s,event,sequence):
        if s in self.queue or s in self.offers or self.room(s)is not None:
            return[wire.selection(-1)]if event.kind==0xa89 else[wire.mode(-1)]
        self.town(s)
        party=self.world.party_of.get(s)
        if party and not party.get('racing')and party['leader']is not s:return[wire.mode(-1)]
        if party:
            for m in party['members']:self.town(m)
        from els_server.domain.mount_racing_selection import handle
        response=handle(s,event,sequence)
        if response[0].payload[:4]!=bytes(4):return response
        if event.kind==0xa8b:
            if getattr(s,'racing_mode',False)and party:
                after=dict(party,racing=True,dungeon=150060,ready=set())
                boxes=_prepared_boxes([(m,self.notices(after,reset=True))for m in after['members']],response)
                party.update(racing=True,dungeon=150060);party['ready'].clear();self.publish(boxes)
            elif not getattr(s,'racing_mode',False)and party and party.get('racing'):
                self.world.leave_party(s)
        if party and party.get('racing')and s in party['members']:
            notice=wire.member_mount(s.account.uid,getattr(s,'racing_selected_mount',None),getattr(s,'racing_mode',False))
            self.publish(_prepared_boxes([(m,[notice])for m in party['members']],response))
        return response

    def invite(self,s,event):
        request=social.party_invite_request(event.payload,settings=True);self.mount(s)
        party=self.world.party_of.get(s)
        if request['dungeon']!=150060 or party and(not party.get('racing')or party['leader']is not s or len(party['members'])>=6):raise ValueError('Racing invitation leader/room')
        target=next((m for m in self.world.members if m.account.character()['name']==request['name']and request['uid']in(0,m.account.uid)),None)
        now=time.monotonic()
        if target in self.invitations and self.invitations[target][2]<=now:self.invitations.pop(target)
        if(target is None or target is s or target in self.world.party_of or target in self.queue or target in self.offers
           or s in self.queue or s in self.offers or target in self.invitations):raise ValueError('Racing invitation target unavailable')
        self.town(target);guards=[pvp_actor.capture(self.world,m)for m in(s,target)]
        s.invite_times=type(s.invite_times)(t for t in s.invite_times if now-t<30)
        if len(s.invite_times)>=5:raise ValueError('Racing invitation rate')
        response=[social.party_invite_ack(target.account.character())]
        boxes=_prepared_boxes([(target,[social.party_invited(s.account.character(),target.account.character())])],response)
        for guard in guards:guard()
        self.invitations[target]=(s,party,now+30,_binding(s),_binding(target));s.invite_times.append(now)
        self.publish(boxes);return response

    def answer(self,s,event):
        first,second,accepted=social.party_answer_request(event.payload)
        inviter,party,deadline,before,receiver=self.invitations[s]
        if(first!=inviter.account.uid or second not in(0,s.account.uid)or deadline<time.monotonic()
           or not _same(inviter,before)or not _same(s,receiver)or self.world.party_of.get(inviter)is not party
           or s in self.world.party_of or inviter in self.queue or inviter in self.offers):raise ValueError('Original racing invitation required')
        self.town(s);self.mount(inviter)
        if not accepted:self.invitations.pop(s);return[social.party_answer_ack(inviter.account.uid)]
        if party and(party['leader']is not inviter or party['run']is not None or len(party['members'])>=6):raise ValueError('Racing invitation room changed')
        members=[*(party['members']if party else[inviter]),s]
        for m in members:self.town(m)
        after=dict(party,members=members,ready=set())if party else dict(id=self.world.next_party,leader=inviter,members=members,ready=set(),dungeon=150060,difficulty=0,mode=0,run=None,raid_party=False,racing=True)
        guards=[pvp_actor.capture(self.world,m)for m in members];response=[social.party_answer_ack(inviter.account.uid)]
        boxes=_prepared_boxes([(m,self.notices(after,reset=party is not None))for m in members],response)
        for guard in guards:guard()
        if party is None:
            party=after;self.world.next_party+=1;self.world.parties[party['id']]=party
            self.world.party_of[inviter]=party
        else:party['members'][:]=members;party['ready'].clear()
        self.world.party_of[s]=party;self.invitations.pop(s);self.publish(boxes)
        return response

    def admit(self,members,leader,party=None):
        members=tuple(members)
        if not 3<=len(members)<=6:raise ValueError('Racing real participant count')
        mounts={m:self.mount(m)for m in members}
        if len({Path(m.account.store.path).resolve()for m in members})!=1:raise ValueError('Racing original shared store')
        guards=[pvp_actor.capture(self.world,m)for m in members]
        identity=self.next_identity;event,slots=wire.admission(members,leader,identity,mounts,leader.port_probe_port)
        deliveries=[(m,[event])for m in members]
        for key in {self.world.members[m]for m in members}:
            removed=[m.account.uid for m in members if self.world.members[m]==key]
            notice=social.town_members(removed=removed)
            deliveries.extend((other,[notice])for other in self.world.towns[key]if other not in members)
        boxes=_prepared_boxes(deliveries,())
        for guard in guards:guard()
        participants=tuple((m.account.uid,m.account.account_id,mounts[m]['uid'])for m in members)
        room=Room(identity,str(uuid.uuid4()),members,tuple(_binding(m)for m in members),mounts,slots,participants,party)
        self.next_identity+=1
        for m in members:
            key=self.world.members.pop(m);self.world.towns[key].pop(m)
            if not self.world.towns[key]:self.world.towns.pop(key)
            self.queue.pop(m,None);self.offers.pop(m,None);self.gates.pop(m,None)
            self.rooms[m]=room;m.phase='racing_loading';m.active_map=m.pending_map=150060
        if party:party['run']=room
        self.publish(boxes)

    def current(self,s,room):
        if(self.rooms.get(s)is not room or not _same(s,room.bindings[room.members.index(s)])
           or s.phase!='racing_'+room.phase or s.active_map!=150060 or s.pending_map!=150060):raise ValueError('Original racing room actor changed')
        pvp_actor.actor(self.world,s)

    def loaded(self,s,event):
        room=self.room(s);self.current(s,room);value=loading.progress_request(event.payload)
        if room.phase not in('loading','active')or value<room.progress.get(s,0):raise ValueError('Racing loading progress')
        progress=dict(room.progress);progress[s]=value;members=room.members
        guards=[pvp_actor.capture(self.world,m)for m in members]
        response=[loading.progress_ack(value)]
        deliveries=[(m,[loading.progress_notice(s.account.uid,value)])for m in members]
        start=room.phase=='loading'and all(progress.get(m)==100 for m in members)
        def prepare(db):
            for m,guard in zip(members,guards):guard();self.current(m,room)
        if start:
            roster=room.participants
            def encode(db,data):
                play=wire.play_start(room.slots);boosters=wire.booster_map(data['plans'])
                return _prepared_boxes([(m,events+[play,boosters])for m,events in deliveries],response)
            data,boxes=mount_races.begin(s.account.store.path,room.seed,roster,prepare=prepare,encode=encode)
            room.data=data;room.started=time.monotonic();room.phase='active'
            for m in members:m.phase='racing_active'
        else:boxes=_prepared_boxes(deliveries,response);prepare(None)
        room.progress=progress;self.publish(boxes);return response

    def finish(self,s,event):
        room=self.room(s);self.current(s,room)
        wire.finish_request(event.payload,[p[0]for p in room.participants])
        if room.phase not in('active','result'):raise ValueError('Racing is not running')
        if room.started is None or time.monotonic()-room.started<max(r['time']for r in room.data['standings']):raise ValueError('Racing finish too early')
        return self.settle_room(s,room)

    def settle_room(self,s,room):
        current=[m for m in room.members if self.room(m)is room]
        guards=[pvp_actor.capture(self.world,m)for m in current]
        def prepare(db):
            for m,guard in zip(current,guards):guard();self.current(m,room)
        response=[wire.finish_ack()]
        def encode(db,data,rows):
            roster={uid:r['mount']for uid,r in rows.items()}
            return _prepared_boxes([(m,[wire.result(data,**rows[m.account.uid],roster=roster)])for m in current],response)
        boxes=mount_races.settle(s.account.store.path,room.seed,[(owner,account)for owner,account,uid in room.participants],prepare=prepare,encode=encode)
        room.phase='result'
        for m in current:m.phase='racing_result'
        self.publish(boxes);return response

    def leave(self,s,event):
        room=self.room(s);self.current(s,room)
        if not 100<=len(event.payload)<=8192 or event.payload[:4]!=struct.pack('>i',0x72):raise ValueError('Racing native return payload')
        mount_races.leave(s.account.store.path,s.account.uid)
        from els_server.protocol.dungeon_messages import end_ack
        response=[end_ack(),s.saved_user_sync()]
        for reply in response:encode_event(reply)
        self.remove(s);s.phase='map_loading';s.pending_map=None;s.dungeon_return_pending=True;s.inventory_town_sync_sent=True
        return response

    def remove(self,s):
        room=self.rooms.pop(s,None)
        if room and room.party and not any(self.room(m)is room for m in room.members):room.party['run']=None;room.party['ready'].clear()

    def disconnect(self,s):
        self.gates.pop(s,None);self.cancel(s);self.invitations={m:v for m,v in self.invitations.items()if m is not s and v[0]is not s}
        room=self.room(s)
        if room:
            index=room.members.index(s);owner=room.participants[index][0];path=room.bindings[index][1][3]
            mount_races.leave(path,owner);self.remove(s)
            if room.phase=='loading':
                for other in room.members:
                    if self.room(other)is room:other.coop_error='Racing ended before all participants loaded'

    def relay_lost(self,s):
        room=self.room(s)
        if room is not None and room.phase!='result':
            self.disconnect(s);s.coop_error='Racing relay disconnected'

    def cancel(self,s):
        offer=self.offers.get(s);members=offer.members if offer else(self.world.party_of[s]['members']if s in self.queue and s in self.world.party_of else(s,))
        notice=Event(0x201,kind=0x387,payload=bytes(4)+wstring(''))
        for m in members:
            binding=offer.bindings[offer.members.index(m)]if offer else self.queue.get(m)
            if binding is not None and _same(m,binding):self.world.send(m,notice)
            self.queue.pop(m,None);self.offers.pop(m,None)
        self.partial_since=None

    def match(self):
        members=[]
        for s,binding in tuple(self.queue.items()):
            try:
                if not _same(s,binding):raise ValueError('Racing queue actor changed')
                self.mount(s)
            except(ValueError,sqlite3.Error):self.cancel(s);continue
            members.append(s)
        if len(members)>=6:self.admit(members[:6],members[0]);self.partial_since=None;return
        if len(members)<3:self.partial_since=None;return
        now=time.monotonic()
        if self.partial_since is None:self.partial_since=now;return
        from els_server.domain.mount_racing_rules import policy
        if now-self.partial_since<policy()['partial_match_wait_seconds']:return
        offer=Offer(self.next_identity,tuple(members),tuple(self.queue[m]for m in members),deadline=now+30);self.next_identity+=1
        notice=Event(0x201,kind=0x388,payload=struct.pack('>QiiBBBB',offer.identity,len(members),150060,0,0,0,1))
        boxes=_prepared_boxes([(m,[notice])for m in members],())
        for m in members:self.queue.pop(m);self.offers[m]=offer
        self.partial_since=None;self.publish(boxes)

    def periodic(self,s):
        if s in self.queue:self.match()
        offer=self.offers.get(s)
        if offer and time.monotonic()>offer.deadline:self.cancel(s)
        room=self.room(s)
        if room and room.phase=='loading'and any(m.released for m in room.members):self.disconnect(s)
        if room and room.phase=='active':
            from els_server.domain.mount_racing_plan import physics
            finish=max(r['time']for r in room.data['standings'])
            # The client reports once using its own render clock. The saved
            # server finish clock must also complete a race if that report
            # arrived early; no client retransmission is needed for rewards.
            if(time.monotonic()-room.started>=finish+physics()['race']['AllFinishStateTime']
               and int(time.time())>=room.data['started']+math.ceil(finish)):
                self.current(s,room);self.settle_room(s,room)

    def request(self,s,event,sequence):
        if event.event_id!=0x202:return None
        kind=event.kind;room=self.room(s);party=self.world.party_of.get(s)
        waiting=s in self.queue or s in self.offers
        if waiting and kind not in(0x385,0x389,0x85):return[]
        selected=getattr(s,'racing_mode',False)
        relevant=(kind in(0xa89,0xa8b,0xa86)or room is not None
          or kind==0x7d4 and event.payload[4:]==struct.pack('>i',150060)
          or kind in(0x37f,0x382,0x385,0x389)and(selected or s in self.queue or s in self.offers)
          or kind in(0x136,0x139,0x13f,0x14c,0x14e,0x151,0x145)and(selected or party and party.get('racing')or s in self.invitations))
        if not relevant:return None
        if room and kind not in(0x91,0xa86,0x67):return []
        reply_guard=pvp_actor.safe_capture(self.world,s)
        if reply_guard is None:return[]
        try:
            if not _envelope(event)or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Racing original envelope/sequence')
            if kind in(0xa89,0xa8b):return self.selection(s,event,sequence)
            if room:
                if kind==0x91:return self.loaded(s,event)
                if kind==0xa86:return self.finish(s,event)
                if kind==0x67:return self.leave(s,event)
            if kind==0x136:return self.invite(s,event)
            if kind==0x139:return self.answer(s,event)
            if kind==0x7d4:
                mode,identity=struct.unpack('>ii',event.payload);self.mount(s)
                if(identity!=150060 or mode not in(1,2)
                   or party and(party['leader']is not s or mode==2 and len(party['members'])==6)
                   or mode==1 and(not party or len(party['members'])<3)):
                    raise ValueError('Racing entry mode/roster')
                self.gates[s]=(mode,time.monotonic()+30,_binding(s));return[Event(0x201,kind=0x7d5,payload=struct.pack('>ii',0,mode))]
            if kind in(0x37f,0x382):
                gate=self.gates.get(s);mode=2 if kind==0x37f else 1
                # Native current-party start2D6D830 sends382 directly, as
                # ordinary party entry does. Random matching uses7D4 first.
                direct=mode==1 and party and party.get('racing')and party['leader']is s
                if not direct and(gate is None or gate[0]!=mode or gate[1]<time.monotonic()or not _same(s,gate[2])):raise ValueError('Racing original entry preflight required')
                if not 23<=len(event.payload)<=86 or not any(struct.unpack_from('>I',event.payload,o)[0]==len(event.payload)-22 for o in range(19)):raise ValueError('Racing original opaque entry')
                members=tuple(party['members'])if party else(s,)
                if party and(not party.get('racing')or party['leader']is not s or party['run']is not None):raise ValueError('Racing current leader required')
                if mode==2 and len(members)==6:raise ValueError('Six-member racing party uses current start')
                for m in members:self.mount(m)
                from els_server.protocol.dungeon_messages import entry_ack
                response=[entry_ack(0x380 if mode==2 else 0x383)]
                if mode==1:self.admit(members,s,party)
                else:
                    if any(m in self.queue or m in self.offers for m in members):raise ValueError('Already matching')
                    self.queue.update((m,_binding(m))for m in members);self.gates.pop(s,None);self.match()
                return response
            if kind==0x385:
                if len(event.payload)!=8:raise ValueError('Native racing cancel UID')
                self.cancel(s);return[Event(0x201,kind=0x386,payload=bytes(7))]
            if kind==0x389:
                offer=self.offers.get(s)
                if offer is None or event.payload not in(b'\0\1',b'\1\1')or time.monotonic()>offer.deadline:raise ValueError('Original partial racing offer required')
                response=[Event(0x201,kind=0x38a,payload=struct.pack('>iQi',0,s.account.uid,0)+wstring('')+struct.pack('>i',150060))]
                if not event.payload[0]:self.cancel(s);return response
                offer.accepted.add(s)
                if len(offer.accepted)==len(offer.members):self.admit(offer.members,offer.members[0])
                return response
            if kind==0x13f:
                if len(event.payload)!=4:raise ValueError('Racing party leave')
                if s in self.queue or s in self.offers:self.cancel(s)
                self.world.leave_party(s);return[ack(0x140)]
            if kind==0x14c:
                if not party or len(event.payload)!=5 or event.payload[0]>1:raise ValueError('Racing ready state')
                self.mount(s)
                boxes=_prepared_boxes([(m,[social.party_ready_notice(s.account.uid,bool(event.payload[0]))])for m in party['members']],())
                if event.payload[0]:party['ready'].add(s)
                else:party['ready'].discard(s)
                self.publish(boxes);return[]
            if kind in(0x14e,0x151):
                if not party or party['leader']is not s or party['run']is not None or len(event.payload)!=8 or any(m in self.queue or m in self.offers for m in party['members']):raise ValueError('Racing leader action')
                target=next((m for m in party['members']if m.account.uid==struct.unpack('>Q',event.payload)[0]),None)
                if target is None or target is s:raise ValueError('Racing leader target')
                if kind==0x151:self.world.leave_party(target)
                else:
                    after=dict(party,leader=target,ready=set())
                    boxes=_prepared_boxes([(m,self.notices(after,reset=True))for m in party['members']],[ack(kind+1)])
                    reply_guard();party['leader']=target;party['ready'].clear();self.publish(boxes)
                return[ack(kind+1)]
            return[]
        except(ValueError,KeyError,struct.error,sqlite3.Error)as error:
            s._mount_racing_rejection=str(error)
            try:reply_guard()
            except(ValueError,AttributeError,KeyError,TypeError):return[]
            if kind==0xa89:return[wire.selection(-1)]
            if kind==0xa8b:return[wire.mode(-1)]
            if kind==0xa86:return[wire.finish_ack(-1)]
            if kind==0x136:return[social.party_invite_ack(result=-1)]
            if kind==0x139:return[social.party_answer_ack(result=-1)]
            if kind==0x7d4:return[Event(0x201,kind=0x7d5,payload=struct.pack('>ii',2,1))]
            if kind in(0x37f,0x382):
                from els_server.protocol.dungeon_messages import entry_ack
                return[entry_ack(0x380 if kind==0x37f else 0x383,2)]
            if kind in(0x14e,0x151):return[ack(kind+1,-1)]
            if kind==0x14c:return[social.party_ready_notice(s.account.uid,False,-1)]
            if kind==0x91:return[loading.progress_ack(room.progress.get(s,0),2)]
            if kind==0x385:return[Event(0x201,kind=0x386,payload=struct.pack('>i',2)+bytes(3))]
            if kind==0x389:return[Event(0x201,kind=0x38a,payload=struct.pack('>iQi',2,s.account.uid,0)+wstring('')+struct.pack('>i',150060))]
            return[]

    def routing(self,app,room):
        current=tuple(m for m in room.members if self.room(m)is room)
        try:
            for m in current:
                if m.application is not app or app.playing.get(m.account.account_id)is not m:
                    raise ValueError('Racing transport current account')
                self.current(m,room)
        except(ValueError,AttributeError,KeyError):return {}
        peers=[dict(uid=m.account.uid,port=21100+i)for i,m in enumerate(room.members)]
        return {m.account.account_id:(dict(epoch=room.seed,uid=m.account.uid,peers=peers),
            {(m.account.account_id,room.seed,other.account.uid):(other.account.account_id,m.account.uid)
                for other in current if other is not m})for m in current}

    def manifest(self,app,account_id):
        room=self.room(app.playing.get(account_id))
        if room is None:return None
        value=self.routing(app,room).get(account_id)
        return None if value is None else value[0]

    def relay_target(self,app,account_id,epoch,target):
        manifest=self.manifest(app,account_id)
        if manifest is None or manifest['epoch']!=epoch:return None
        s=app.playing[account_id];room=self.room(s)
        other=next((m for m in room.members if m is not s and m.account.uid==target and self.room(m)is room),None)
        return None if other is None else(other.account.account_id,s.account.uid)
