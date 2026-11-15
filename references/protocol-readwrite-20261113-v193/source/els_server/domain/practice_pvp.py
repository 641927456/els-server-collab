"""Native free-practice lobby, two-player room and no-economy round return."""
from dataclasses import dataclass,field
import secrets,struct,time,uuid
from els_server.domain import pvp_actor
from els_server.domain.party_commands import _prepared_boxes
from els_server.domain.pvp_registration import Ticket,_binding,_same,_envelope
from els_server.protocol import practice_pvp_messages as wire
from els_server.protocol import pvp_room_messages,dungeon_messages,social_messages


@dataclass(eq=False)
class Waiting:
    identity:int
    title:str
    password:str
    map_id:int
    members:tuple
    seconds:int=200
    ready:frozenset=field(default_factory=frozenset)
    battle:object=None


class Practice:
    def __init__(self,pvp):
        self.pvp=pvp;self.world=pvp.world
        self.visitors={};self.rooms={};self.members={};self.ready_requests={}

    def signature(self):
        return (tuple(self.visitors.items()),tuple(self.members.items()),
            tuple((key,r,r.title,r.password,r.map_id,r.members,r.ready,r.battle,r.seconds)
                for key,r in self.rooms.items()),tuple(self.ready_requests.items()))

    def capture(self,s):
        guard=pvp_actor.capture(self.world,s);source=self.signature()
        def check():
            guard()
            if self.signature()!=source:raise ValueError('Practice room source changed during encoding')
        return check

    def current(self,s,*,waiting=False):
        binding=self.visitors.get(s)
        if binding is None or not _same(s,binding):raise ValueError('Practice current lobby owner')
        pvp_actor.actor(self.world,s)
        room=self.members.get(s)
        if (s.phase!=('practice_waiting'if room is not None else'practice_lobby')
                or s in self.world.members or s in self.world.party_of
                or self.world.dungeons.transport_room(s)is not None
                or self.pvp.room(s)is not None or not self.pvp.support_ready(s)
                or waiting and room is None):
            raise ValueError('Practice current free-channel lobby/room')
        return room

    def slots(self,room,*,members=None,ready=None):
        members=room.members if members is None else members
        ready=room.ready if ready is None else ready
        return tuple(wire.slot(members[i]if i<len(members)else None,i,
            state=3 if i<len(members)else 1,host=i==0 and bool(members),
            ready=i<len(members)and members[i]in ready)for i in range(2))

    def commit(self,s,deliveries,response,checks,mutate):
        boxes=_prepared_boxes(deliveries,response)
        for check in checks:check()
        mutate()
        for member,box in boxes.items():member.mailbox=box
        return response

    def enter(self,s,event):
        if event.payload:raise ValueError('Practice native empty entry')
        pvp_actor.town(self.world,s,minimum_level=1)
        if (s in self.pvp.registrations.queue or s in self.pvp.registrations.offers
                or s in self.pvp.duels.pending or s in self.visitors):
            raise ValueError('Practice conflicting current PvP registration')
        guard=pvp_actor.capture(self.world,s)
        key=self.world.members[s];old=self.world.towns[key]
        checks=[guard]+[pvp_actor.capture(self.world,p)for p in old if p is not s]
        notice=social_messages.town_members(removed=[s.account.uid])
        deliveries=[(p,(notice,))for p in old if p is not s]
        binding=_binding(s)
        def apply():
            self.world.members.pop(s);old.pop(s)
            if not old:self.world.towns.pop(key)
            self.visitors[s]=binding;s.phase='practice_lobby'
        return self.commit(s,deliveries,[wire.channels()],checks,apply)

    def create(self,s,event):
        self.current(s)
        if s in self.members:raise ValueError('Practice already in a room')
        guard=self.capture(s)
        value=wire.create_request(event.payload)
        map_id=value['map']
        if map_id<0:map_id=secrets.choice(tuple(sorted(pvp_room_messages.TEAM_MAPS)))
        room=Waiting(secrets.randbelow(2**63-1)+1,value['title'],value['password'],map_id,(s,),int(value['seconds']))
        slots=self.slots(room)
        response=[wire.entered(0x5f,wire.room_info(room,s.port_probe_port),slots)]
        def apply():
            self.rooms[room.identity]=room;self.members[s]=room;s.phase='practice_waiting'
        return self.commit(s,(),response,(guard,),apply)

    def join(self,s,event):
        self.current(s)
        if s in self.members:raise ValueError('Practice already joined')
        uid,password=wire.join_request(event.payload)
        return self.join_room(s,uid,password)

    def join_room(self,s,uid,password,*,reply=0x63):
        room=self.rooms.get(uid)
        if room is None or len(room.members)!=1 or room.battle is not None or password!=room.password:
            raise ValueError('Practice room unavailable or password mismatch')
        host=room.members[0];self.current(host,waiting=True)
        if host.account.account_id==s.account.account_id:raise ValueError('Practice distinct account owners')
        checks=(self.capture(host),self.capture(s))
        members=room.members+(s,);slots=self.slots(room,members=members)
        response=[wire.entered(reply,wire.room_info(room,s.port_probe_port,count=2),slots)]
        def apply():
            room.members=members;self.members[s]=room;s.phase='practice_waiting'
        return self.commit(s,[(host,(wire.joined(slots[1],2),))],response,checks,apply)

    def quick_join(self,s,event):
        self.current(s)
        if s in self.members or event.payload!=bytes(5):
            raise ValueError('Practice native ordinary team quick join')
        available=next((r for r in self.rooms.values()if r.battle is None
            and not r.password and len(r.members)==1
            and r.members[0].account.account_id!=s.account.account_id),None)
        if available is not None:return self.join_room(s,available.identity,'',reply=0x66)
        guard=self.capture(s)
        room=Waiting(secrets.randbelow(2**63-1)+1,'Practice1v1','',
            secrets.choice(tuple(sorted(pvp_room_messages.TEAM_MAPS))),(s,))
        response=[wire.entered(0x66,wire.room_info(room,s.port_probe_port),self.slots(room))]
        def apply():
            self.rooms[room.identity]=room;self.members[s]=room;s.phase='practice_waiting'
        return self.commit(s,(),response,(guard,),apply)

    def ready(self,s,event,sequence):
        room=self.current(s,waiting=True)
        if event.payload!=b'\0' or room.battle is not None:
            raise ValueError('Practice original ordinary ready toggle')
        previous=self.ready_requests.get(s)
        if previous is not None and previous[:3]==(room,sequence,event.payload):return list(previous[3])
        checks=tuple(self.capture(m)for m in room.members)
        ready=room.ready.symmetric_difference((s,))
        slots=self.slots(room,ready=ready);index=room.members.index(s)
        response=[wire.event(0x8f,struct.pack('>i?',0,s in ready))]
        def apply():
            room.ready=ready;self.ready_requests[s]=(room,sequence,event.payload,tuple(response))
        return self.commit(s,[(m,(wire.prepared(slots[index]),))for m in room.members],response,checks,apply)

    def start(self,s,event):
        room=self.current(s,waiting=True)
        map_id,client_seed=wire.start_request(event.payload)
        if (room.members[0]is not s or len(room.members)!=2 or room.battle is not None
                or room.members[1]not in room.ready):
            raise ValueError('Practice host and ready opposing player required')
        for m in room.members:self.current(m,waiting=True)
        if map_id<0:map_id=room.map_id
        checks=tuple(self.capture(m)for m in room.members)
        generation=str(uuid.uuid4())
        tickets=tuple(Ticket(m,generation,_binding(m),generation,None,time.monotonic())for m in room.members)
        battle,_=self.pvp.loading.prepare(room.members,tickets,room.identity,generation,
            pvp_room_messages.TEAM_MAPS-{map_id},s.port_probe_port,kind='practice',seconds=room.seconds)
        notice=wire.start_notice(map_id,battle.slots,client_seed)
        response=[wire.event(0x8c,bytes(4))]
        def apply():
            room.map_id=map_id;room.battle=battle
            for m in room.members:
                self.pvp.loading.rooms[m]=battle;m.phase='pvp_loading';m.active_map=m.pending_map=map_id
        return self.commit(s,[(m,(notice,))for m in room.members],response,checks,apply)

    def finish(self,s,payload,*,ack=True):
        battle=self.pvp.room(s);room=self.members.get(s)
        if room is None or room.battle is not battle:raise ValueError('Practice active room generation')
        if battle.phase in('active','reporting'):
            self.pvp.rounds.leave(s);self.pvp._settle(s)
        if battle.phase not in('result','loading'):raise ValueError('Practice return phase')
        # The native channel9 end handler restores its existing waiting room;
        # challenge15 alone takes the direct saved-town branch.
        response=([dungeon_messages.end_ack()]if ack else[])+[s.saved_user_sync()]
        guard=self.capture(s)
        _prepared_boxes((),response);guard()
        response=s.mailbox.drain()+response
        self.pvp._remove(s);s.phase='practice_waiting'
        s.active_map=s.pending_map=s.account.get_location()['map']
        s.pvp_end_payload=bytes(payload)
        if not any(self.pvp.room(m)is battle for m in room.members):
            room.battle=None;room.ready=frozenset()
            for m in room.members:self.ready_requests.pop(m,None)
        return response

    def leave(self,s,event,*,battle_exit=False):
        if event.payload:raise ValueError('Practice original room exit body')
        room=self.current(s,waiting=True)
        if room.battle is not None and not battle_exit:raise ValueError('Practice peer has not returned from battle')
        checks=tuple(self.capture(m)for m in room.members if not m.released)
        remaining=tuple(m for m in room.members if m is not s)
        slots=self.slots(room,members=remaining,ready=frozenset())
        # Self-departure needs its original slot until C90480 changes scene.
        own_notice=wire.departed(s.account.uid,self.slots(room))
        response=[wire.event(0x6b,bytes(4)),own_notice]
        def apply():
            self.members.pop(s);self.ready_requests.pop(s,None);s.phase='practice_lobby'
            room.members=remaining;room.ready=frozenset()
            if not remaining:self.rooms.pop(room.identity)
        return self.commit(s,[(m,(wire.departed(s.account.uid,slots),))for m in remaining],response,checks,apply)

    def town(self,s,event,sequence):
        self.current(s)
        if s in self.members or event.payload!=struct.pack('>iB',s.account.get_location()['map'],0):
            raise ValueError('Practice saved-town return requires lobby departure')
        guard=self.capture(s);response=[s.saved_user_sync()]
        _prepared_boxes((),response);guard()
        self.visitors.pop(s);self.ready_requests.pop(s,None)
        s.phase='map_loading';s.pending_map=None;s.dungeon_return_pending=True
        s.inventory_town_sync_sent=True
        return response+s.handle(event,sequence)

    def request(self,s,event,sequence):
        try:return self._request(s,event,sequence)
        except ValueError:
            kind=event.kind
            if kind not in(0x4c,0x4e,0x55,0x5e,0x62,0x65,0x8e,0x8b,0x6a,0x225):raise
            if kind==0x225:return [wire.event(0x226,struct.pack('>i',1))]
            body=struct.pack('>i',1)
            if kind==0x4c:body+=struct.pack('>II',wire.CHANNEL,0)
            if kind==0x55:body+=struct.pack('>IIIQ',1,1,0,0)
            if kind==0x8e:body+=b'\0'
            return [wire.event(kind+1,body)]

    def _request(self,s,event,sequence):
        kind=event.kind
        if kind==0x4c:
            if not _envelope(event):return []
            return self.enter(s,event)
        if s not in self.visitors or self.pvp.room(s)is not None:return None
        if not _envelope(event):return []
        if kind==0x55:
            self.current(s);page,mode,identity=wire.list_request(event.payload)
            rooms=[r for r in self.rooms.values()if r.battle is None
                and mode in(-1,0)and(identity in(-1,0)or r.identity==identity)]
            pages=max(1,(len(rooms)+7)//8)
            if page>pages:raise ValueError('Practice original room-list page')
            rows=[wire.room_info(r,s.port_probe_port,listing=True)for r in rooms[(page-1)*8:page*8]]
            return [wire.room_list(page,rows,pages=pages)]
        if kind==0x4e:
            self.current(s)
            if event.payload!=struct.pack('>I',wire.CHANNEL):raise ValueError('Practice unavailable channel')
            return [wire.event(0x4f,bytes(4))]
        if kind==0x5e:return self.create(s,event)
        if kind==0x62:return self.join(s,event)
        if kind==0x65:return self.quick_join(s,event)
        if kind==0x8e:return self.ready(s,event,sequence)
        if kind==0x8b:return self.start(s,event)
        if kind==0x6a:return self.leave(s,event)
        if kind==0x225:return self.town(s,event,sequence)
        if kind==0x7d4:
            mode=struct.unpack('>i',event.payload[:4])[0]if len(event.payload)>=4 else 5
            return [wire.event(0x7d5,struct.pack('>ii',1,mode))]
        if kind==0x342:
            from els_server.protocol.pvp_match_messages import registration_ack
            return [registration_ack(1,False,'')]
        if kind==0x34a:return []
        if kind==0x5c6:
            from els_server.protocol.duel_messages import requested,invitation_request
            return [requested(invitation_request(event.payload)['target'],1678)]
        return None

    def disconnect(self,s):
        self.visitors.pop(s,None);self.ready_requests.pop(s,None)
        room=self.members.pop(s,None)
        if room is None:return
        remaining=tuple(m for m in room.members if m is not s)
        room.members=remaining;room.ready=frozenset()
        if not remaining:self.rooms.pop(room.identity,None)
        elif room.battle is None:
            notice=wire.departed(s.account.uid,self.slots(room))
            boxes=_prepared_boxes([(m,(notice,))for m in remaining],())
            for m,box in boxes.items():m.mailbox=box
