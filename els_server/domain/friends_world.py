"""Friends-only town membership and bounded, authenticated cross-session mail.

All methods run in Application's single worker. The transport owns encryption,
sequence numbers and socket writes; no foreign session's packet is pre-encoded.
"""
from collections import deque
import time
from els_server.protocol import social_messages as wire
from els_server.domain.local_session import SessionOrderError


class Mailbox:
    def __init__(self):self.messages=deque();self.moves={};self.bytes=0

    def append(self,message,move_uid=None):
        size=len(message.payload)
        if move_uid is not None:
            old=self.moves.get(move_uid)
            if old is not None:self.bytes-=len(old.payload)
            self.moves[move_uid]=message
        else:self.messages.append(message)
        self.bytes+=size
        if len(self.messages)+len(self.moves)>256 or self.bytes>256*1024:
            raise SessionOrderError('Social consumer is too slow')

    def drain(self):
        values=list(self.messages)+list(self.moves.values())
        self.messages.clear();self.moves.clear();self.bytes=0
        return values


class FriendsWorld:
    def __init__(self):
        self.towns={};self.members={};self.parties={};self.party_of={}
        self.invitations={};self.next_party=900001
        from els_server.domain.friends_dungeon import FriendsDungeons
        self.dungeons=FriendsDungeons(self)
        from els_server.domain.field_boss import FieldBosses
        self.field_bosses=FieldBosses(self)

    def disconnect(self,session):
        self.field_bosses.detach(session)
        self.leave(session)
        self.leave_party(session)
        self.invitations={s:v for s,v in self.invitations.items() if s is not session and v['inviter'] is not session}

    def party_snapshot(self,party,reset=False):
        notice=wire.party_snapshot(party)
        for member in list(party['members']):
            if reset:self.send(member,wire.party_removed())
            self.send(member,notice)

    def leave_party(self,session):
        current=self.party_of.get(session)
        if current and (current.get('challenge') or current.get('challenge_pending')):
            from els_server.domain.group_challenge import cancel
            cancel(self,current)
        self.dungeons.detach(session)
        party=self.party_of.pop(session,None)
        if party is None:return
        party['members'].remove(session);party['ready'].discard(session)
        self.send(session,wire.party_removed(session.account.uid))
        if len(party['members'])<2:
            for other in list(party['members']):
                self.party_of.pop(other,None);self.send(other,wire.party_removed(session.account.uid))
            self.parties.pop(party['id'],None)
        else:
            if party['leader'] is session:party['leader']=party['members'][0]
            self.party_snapshot(party,reset=True)

    def party_request(self,session,event):
        kind=event.kind
        if event.event_id==0x202 and kind==0x145:
            from els_server.domain.party_selection import select
            return select(self,session,event)
        if kind not in (0x136,0x139,0x13f,0x14c):return None
        if session.phase!='town_ready' or session not in self.members:
            return [wire.party_invite_ack(result=-1)] if kind==0x136 else [wire.party_answer_ack(result=-1)] if kind==0x139 else []
        if self.party_of.get(session,{}).get('solo_challenge') and kind in (0x136,0x139):
            return [wire.party_invite_ack(result=-1)] if kind==0x136 else [wire.party_answer_ack(result=-1)]
        if kind==0x136:
            now=time.monotonic()
            while session.invite_times and now-session.invite_times[0]>=30:session.invite_times.popleft()
            if len(session.invite_times)>=5:return [wire.party_invite_ack(result=-1)]
            try:uid,name,requested=wire.party_invite_request(event.payload,details=True)
            except (ValueError,UnicodeError):return [wire.party_invite_ack(result=-1)]
            target=next((s for s in self.members if s.account.character()['name']==name and uid in (0,s.account.uid)),None)
            party=self.party_of.get(session)
            from els_server.domain.raid_party import raid_definition,capacity
            raid=raid_definition(requested)
            if party is not None and (party.get('challenge') or party.get('challenge_pending')):return [wire.party_invite_ack(result=-1)]
            # A request naming a current raid can create/promote that room;
            # ordinary invitations keep their existing four-player bound.
            if raid and (party is None or party['leader'] is session and party['run'] is None):
                from els_server.domain.region_quests import account_dungeon_allowed
                existing=party['members'] if party else [session]
                if not all(s.phase=='town_ready' and account_dungeon_allowed(s.account,requested) for s in existing):return [wire.party_invite_ack(result=-1)]
                if party is not None and (party.get('raid_party') and party['dungeon']!=requested or len(existing)>=raid['maximum']):return [wire.party_invite_ack(result=-1)]
            else:raid=None
            maximum=raid['maximum'] if raid else capacity(party) if party else 4
            if (target is None or target is session or target in self.party_of
                or party is not None and (party['leader'] is not session or party['run'] is not None or len(party['members'])>=maximum)
                or target in self.invitations and self.invitations[target]['expires']>now):return [wire.party_invite_ack(result=-1)]
            session.invite_times.append(now)
            self.invitations[target]={'inviter':session,'expires':now+30,'party':party,'raid_dungeon':requested if raid else None}
            self.send(target,wire.party_invited(session.account.character(),target.account.character()))
            return [wire.party_invite_ack(target.account.character())]
        if kind==0x139:
            try:first,second,accepted=wire.party_answer_request(event.payload)
            except ValueError:return [wire.party_answer_ack(result=-1)]
            invite=self.invitations.get(session)
            if invite is None:return [wire.party_answer_ack(result=-1)]
            inviter=invite['inviter'];uids={session.account.uid,inviter.account.uid}
            # Native 2D60E80 puts the inviter UID first and a zero reserved
            # qword second. The authenticated receiver and pending invitation
            # bind the target; zero never selects another session.
            native_identity=first==inviter.account.uid and second==0
            if (not native_identity and {first,second}!=uids or invite['expires']<time.monotonic() or inviter not in self.members
                or session in self.party_of or self.party_of.get(inviter) is not invite['party']):return [wire.party_answer_ack(result=-1)]
            self.invitations.pop(session)
            if not accepted:return [wire.party_answer_ack(inviter.account.uid)]
            party=invite['party'];reset=party is not None
            from els_server.domain.raid_party import raid_definition,capacity
            requested=invite.get('raid_dungeon');raid=raid_definition(requested) if requested is not None else None
            if (requested is not None and raid is None or party is not None and (party['run'] is not None or party.get('challenge') or party.get('challenge_pending'))):return [wire.party_answer_ack(result=-1)]
            existing=party['members'] if party else [inviter]
            if (party is not None and party['leader'] is not inviter or any(m.released or m.phase!='town_ready' or m not in self.members for m in existing)):
                return [wire.party_answer_ack(result=-1)]
            if raid:
                from els_server.domain.region_quests import account_dungeon_allowed
                if not all(account_dungeon_allowed(m.account,requested) for m in [*existing,session]):return [wire.party_answer_ack(result=-1)]
            if party is None:
                party={'id':self.next_party,'leader':inviter,'members':[inviter], 'ready':set(),'dungeon':requested if raid else 30000,'run':None,'raid_party':bool(raid)}
                self.next_party+=1;self.parties[party['id']]=party;self.party_of[inviter]=party
            elif raid:
                if (party.get('raid_party') and party['dungeon']!=requested or len(party['members'])>=raid['maximum']):return [wire.party_answer_ack(result=-1)]
                party['raid_party']=True;party['dungeon']=requested
            if len(party['members'])>=capacity(party):return [wire.party_answer_ack(result=-1)]
            party['members'].append(session);self.party_of[session]=party
            self.party_snapshot(party,reset=reset)
            return [wire.party_answer_ack(inviter.account.uid)]
        if kind==0x13f:
            if len(event.payload)!=4:return []
            if self.party_of.get(session,{}).get('solo_challenge'):
                from els_server.domain.challenge_flow import store
                store(session).abandon()
            self.leave_party(session)
            from els_server.protocol.protocol_codec import Event
            return [Event(0x201,kind=0x140,payload=bytes(4))]
        if kind==0x14c:
            if len(event.payload)!=5 or event.payload[0] not in (0,1):return []
            party=self.party_of.get(session)
            if party is None:return [wire.party_ready_notice(session.account.uid,False,-1)]
            ready=bool(event.payload[0])
            if ready:party['ready'].add(session)
            else:party['ready'].discard(session)
            for other in party['members']:self.send(other,wire.party_ready_notice(session.account.uid,ready))
            return []

    def room(self,session):return self.towns.get(self.members.get(session),{})

    def send(self,session,message,move_uid=None):
        if session.released:return
        try:session.mailbox.append(message,move_uid)
        except SessionOrderError:session.social_overflow=True

    def leave(self,session):
        key=self.members.pop(session,None)
        if key is None:return
        room=self.towns[key];room.pop(session,None)
        notice=wire.town_members(removed=[session.account.uid])
        for other in list(room):self.send(other,notice)
        if not room:self.towns.pop(key)

    def synchronize(self,session):
        key=(1,session.active_map) if session.role=='game' and session.phase=='town_ready' else None
        if key==self.members.get(session):return
        self.leave(session)
        if key is None:return
        room=self.towns.setdefault(key,{})
        own=(session.account.character(),session.account.get_location(),session.account.get_inventory_snapshot()['items'])
        # Existing login/227 initializes the local actor. Only peer records
        # travel here, avoiding a second restore of the local player.
        self.send(session,wire.town_members(added=list(room.values())))
        notice=wire.town_members(added=[own])
        for other in list(room):self.send(other,notice)
        room[session]=own;self.members[session]=key

    def moved(self,session,payload):
        room=self.room(session)
        if session not in room:return
        character,_,items=room[session]
        room[session]=(character,session.account.get_location(),items)
        message=wire.town_movement(session.account.uid,payload)
        for other in list(room):
            if other is not session:self.send(other,message,session.account.uid)

    def appearance_changed(self,session):
        room=self.room(session)
        if session not in room:return
        before=room[session]
        current=(session.account.character(),session.account.get_location(),session.account.get_inventory_snapshot()['items'])
        if before==current:return
        # Compare the actual public projection: a bag-only expiration must not
        # reconstruct an unchanged remote actor. Never apply anything to self.
        before_wire=wire.town_member(*before)
        current_wire=wire.town_member(*current)
        if before_wire==current_wire:
            room[session]=current
            return
        notice=wire.town_members(added=[current],removed=[session.account.uid])
        # Encode before changing the published projection cache. A rejected
        # instance must not suppress the next qualified refresh attempt.
        room[session]=current
        for other in list(room):
            if other is not session:self.send(other,notice)

    def chat(self,session,event):
        if session.phase not in ('town_ready','dungeon_active') or session.role!='game':return [wire.chat_ack(-1)]
        now=time.monotonic()
        while session.chat_times and now-session.chat_times[0]>=5:session.chat_times.popleft()
        if len(session.chat_times)>=5:return [wire.chat_ack(-1)]
        try:channel,text=wire.chat_request(event.payload)
        except (ValueError,UnicodeError):return [wire.chat_ack(-1)]
        party=self.party_of.get(session)
        if channel==0:
            if session not in self.members:return [wire.chat_ack(-1)]
            recipients=self.room(session)
        else:
            if party is None:return [wire.chat_ack(-1)]
            recipients=party['members']
        session.chat_times.append(now)
        notice=wire.chat_notice(session.account.character(),session.identity['id'],text,channel)
        for other in list(recipients):self.send(other,notice)
        return [wire.chat_ack()]
