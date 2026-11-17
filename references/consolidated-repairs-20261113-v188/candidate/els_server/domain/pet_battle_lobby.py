"""Original invited pet lobby, readiness, start and return; no ordinary party or reward source."""
from dataclasses import dataclass,field
import sqlite3,struct,time,uuid
from els_server.domain.pvp_registration import _binding,_same,_envelope
from els_server.domain import pvp_actor
from els_server.protocol import social_messages as social,pet_battle_lobby_messages as wire
from els_server.protocol.protocol_codec import Event

@dataclass(eq=False)
class Invitation:
    members:tuple
    bindings:tuple
    maps:tuple
    expires:float

@dataclass(eq=False)
class Lobby:
    identity:int
    seed:str
    members:tuple
    bindings:tuple
    maps:tuple
    ready:dict=field(default_factory=dict)
    phase:str='waiting'
    returned:frozenset=frozenset()

def current(flow,state):
    for s,binding,map_id in zip(state.members,state.bindings,state.maps):
        flow.town(s)
        if not _same(s,binding)or s.active_map!=map_id:raise ValueError('Pet lobby source actor retired')
    table=flow.invitations if isinstance(state,Invitation)else flow.lobbies
    if any(table.get(s)is not state for s in state.members):raise ValueError('Pet lobby generation retired')

def forget(table,state):
    for s in state.members:
        if table.get(s)is state:table.pop(s)

def snapshot(lobby):
    # Retain the shared original room constructor's dungeon hint. Kind4 and
    # mode13 select the pet UI; actual battle world comes from34B admission.
    return social.party_snapshot(dict(id=lobby.identity,members=lobby.members,leader=lobby.members[0],
        ready=set(lobby.ready),dungeon=30000,pet_fight=True))

def invite(flow,s,request):
    flow.town(s)
    if flow.busy(s):raise ValueError('Pet invitation while already registered')
    now=time.monotonic()
    while s.invite_times and now-s.invite_times[0]>=30:s.invite_times.popleft()
    if len(s.invite_times)>=5:raise ValueError('Current shared invitation rate limit')
    target=next((m for m in flow.world.members if m.account.character()['name']==request['name']
                 and request['uid']in(0,m.account.uid)),None)
    if target is None or target is s or target.account.account_id==s.account.account_id:
        return[social.party_invite_ack(result=-1)]
    flow.town(target)
    if flow.busy(target):raise ValueError('Pet invitation target occupied')
    if s.account.character()['level']<99 or target.account.character()['level']<99:raise ValueError('Pet lobby99-level actors required')
    state=Invitation((s,target),tuple(_binding(m)for m in(s,target)),tuple(m.active_map for m in(s,target)),time.monotonic()+30)
    replies=[social.party_invite_ack(target.account.character())]
    notice=social.party_invited(s.account.character(),target.account.character(),kind=4)
    boxes=flow.prepare(state.members,[(target,(notice,))],replies)
    for m,binding,map_id in zip(state.members,state.bindings,state.maps):
        flow.town(m)
        if flow.busy(m)or not _same(m,binding)or m.active_map!=map_id:raise ValueError('Pet invitation changed before publication')
    for m in state.members:flow.invitations[m]=state
    s.invite_times.append(now)
    flow.publish(boxes);return replies

def answer(flow,s,event,state):
    if state.members[1]is not s:raise ValueError('Pet invitation current recipient required')
    first,second,accepted=social.party_answer_request(event.payload);inviter=state.members[0]
    if(first!=inviter.account.uid or second not in(0,s.account.uid)or time.monotonic()>=state.expires):raise ValueError('Pet invitation answer binding')
    current(flow,state)
    replies=[social.party_answer_ack(inviter.account.uid)]
    if not accepted:
        boxes=flow.prepare(state.members,[(inviter,(social.party_answer_ack(s.account.uid),))],replies)
        current(flow,state);forget(flow.invitations,state);flow.publish(boxes);return replies
    generation=uuid.uuid4();identity=generation.int&((1<<63)-1)
    if not identity:raise ValueError('Pet lobby generation identity')
    lobby=Lobby(identity,str(generation),state.members,state.bindings,state.maps)
    notice=snapshot(lobby)
    boxes=flow.prepare(state.members,[(m,(notice,))for m in state.members],replies)
    current(flow,state)
    for m in state.members:
        if m in flow.lobbies or m in flow.queue or m in flow.offers:raise ValueError('Pet lobby concurrent admission')
    forget(flow.invitations,state)
    for m in state.members:flow.lobbies[m]=lobby
    flow.publish(boxes);return replies

def ready(flow,s,event,lobby):
    current(flow,lobby)
    if lobby.phase!='waiting':raise ValueError('Pet lobby readiness phase')
    selected=wire.selection(event.payload,allow_empty=True)
    from els_server.domain.pet_battle_flow import Ticket
    ticket=Ticket(s,_binding(s),selected)if selected else None
    entrants=flow.cold(ticket)if ticket else()
    # Reuse the exact already qualified native pet record, without decoding it.
    vector=struct.pack('>I',len(entrants))+b''.join(e.record+struct.pack('>iii',e.fact.ability,100,0)for e in entrants)
    replies=[Event(0x201,kind=0xa71,payload=bytes(4)+vector)]
    notices=[(other,(Event(0x201,kind=0xa72,payload=struct.pack('>Q',s.account.uid)+vector),))for other in lobby.members if other is not s]
    boxes=flow.prepare(lobby.members,notices,replies)
    current(flow,lobby)
    if ticket and flow.cold(ticket)!=entrants:raise ValueError('Pet ready roster changed')
    if ticket:lobby.ready[s]=ticket
    else:lobby.ready.pop(s,None)
    flow.publish(boxes);return replies

def start(flow,s,event,lobby):
    current(flow,lobby)
    guest=lobby.members[1]
    if lobby.phase!='waiting'or lobby.members[0]is not s or guest not in lobby.ready:raise ValueError('Pet lobby leader and ready recipient required')
    selected=wire.selection(event.payload)
    from els_server.domain.pet_battle_flow import Offer,Ticket
    # Native13B gives the host ButtonState2(start), guest3(ready).
    # A73 supplies the host selection; only the guest freezes it via A70.
    tickets=(Ticket(s,_binding(s),selected),lobby.ready[guest])
    offer=Offer(lobby.identity,lobby.seed,tickets)
    def guard():
        current(flow,lobby)
        if lobby.phase!='waiting'or lobby.ready.get(guest)is not tickets[1]:raise ValueError('Pet readiness generation changed')
    replies=flow.admit(s,offer,mode='invited',guard=guard,replies=(wire.start_ack(),))
    lobby.phase='battle';lobby.ready={};lobby.returned=frozenset()
    return replies

def leave(flow,s,event,lobby):
    flow.town(s)
    #30104B0 hide ->2D5B7F0(reason0x6B3) ->2E0CFB0 writes an i32.
    if len(event.payload)!=4:raise ValueError('Pet lobby original self leave')
    notice=social.party_removed(s.account.uid)
    replies=[notice,Event(0x201,kind=0x140,payload=bytes(4))]
    members=tuple(m for m in lobby.members if not m.released)
    boxes=flow.prepare(members,[(m,(notice,))for m in members if m is not s],replies)
    if flow.lobbies.get(s)is not lobby:raise ValueError('Pet leave retired lobby')
    flow.town(s);forget(flow.lobbies,lobby);flow.publish(boxes);return replies

def returned(flow,s,room):
    lobby=flow.lobbies.get(s)
    if room.mode=='invited'and lobby is not None:
        lobby.phase='returning';lobby.returned=lobby.returned|{s}

def periodic(flow,s):
    state=flow.invitations.get(s)
    if state is not None:
        try:
            current(flow,state)
            if time.monotonic()>=state.expires:forget(flow.invitations,state)
        except(ValueError,sqlite3.Error):forget(flow.invitations,state)
    lobby=flow.lobbies.get(s)
    if lobby is not None:
        if lobby.phase=='battle':return
        if lobby.phase=='returning':
            if len(lobby.returned)!=2 or any(m.phase!='town_ready'for m in lobby.members):return
        try:current(flow,lobby)
        except(ValueError,sqlite3.Error):
            # Retire this generation, notifying only actors still in its town
            # source. A member that moved must not receive old party removal
            # in a newer room, and the inviter is not always the one who left.
            remaining=[]
            for m,binding,map_id in zip(lobby.members,lobby.bindings,lobby.maps):
                try:
                    flow.town(m)
                    if flow.lobbies.get(m)is lobby and _same(m,binding)and m.active_map==map_id:remaining.append(m)
                except(ValueError,sqlite3.Error):pass
            forget(flow.lobbies,lobby)
            for m in remaining:
                other=next(p for p in lobby.members if p is not m)
                flow.world.send(m,social.party_removed(other.account.uid))
            return
        if lobby.phase=='returning':
            #225/227 finish Town reconstruction. Native13B only creates a
            # room when PartyManager+8 is empty;13C clears the old room first.
            # Encode each recipient's reset and snapshot together before
            # publishing the restored lobby or changing its server phase.
            notice=snapshot(lobby)
            boxes=flow.prepare(lobby.members,[(m,(social.party_removed(m.account.uid),notice))for m in lobby.members])
            current(flow,lobby)
            lobby.phase='waiting';flow.publish(boxes)

def disconnect(flow,s):
    invitation=flow.invitations.get(s)
    if invitation is not None:forget(flow.invitations,invitation)
    lobby=flow.lobbies.get(s)
    if lobby is not None:
        forget(flow.lobbies,lobby)
        for other in lobby.members:
            if other is not s and not other.released:flow.world.send(other,social.party_removed(s.account.uid))

def handle(flow,s,event,sequence):
    kind=event.kind;state=flow.invitations.get(s);lobby=flow.lobbies.get(s);request=None
    if kind==0x136:
        try:request=social.party_invite_request(event.payload,settings=True,pet_fight=True)
        except(ValueError,UnicodeError):return None
        if request['kind']!=4:return None
    elif not(kind==0x139 and state is not None or kind==0x13f and lobby is not None or kind in(0xa70,0xa73)):
        return None
    guard=pvp_actor.safe_capture(flow.world,s)
    try:
        if not _envelope(event)or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Pet lobby original envelope')
        if request is not None:return invite(flow,s,request)
        if kind==0x139:return answer(flow,s,event,state)
        if lobby is None:raise ValueError('Current pet lobby required')
        if kind==0x13f:return leave(flow,s,event,lobby)
        if kind==0xa70:return ready(flow,s,event,lobby)
        return start(flow,s,event,lobby)
    except(ValueError,sqlite3.Error):
        replies=([social.party_invite_ack(result=-1)]if kind==0x136 else[social.party_answer_ack(result=-1)]if kind==0x139
            else[wire.ready_ack(result=-1)]if kind==0xa70 else[wire.start_ack(-1)]if kind==0xa73 else[Event(0x201,kind=0x140,payload=struct.pack('>i',21))])
        return pvp_actor.failed(guard,lambda:replies)
