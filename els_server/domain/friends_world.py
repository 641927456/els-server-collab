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
        old=self.moves.get(move_uid) if move_uid is not None else None
        count=len(self.messages)+len(self.moves)+(0 if old is not None else 1)
        total=self.bytes+size-(len(old.payload) if old is not None else 0)
        # Admission is atomic: a failed replacement retains the original move
        # object, queue order and byte accounting for the teardown path.
        if count>256 or total>256*1024:
            raise SessionOrderError('Social consumer is too slow')
        if move_uid is not None:self.moves[move_uid]=message
        else:self.messages.append(message)
        self.bytes=total

    def drain(self):
        values=list(self.messages)+list(self.moves.values())
        self.messages.clear();self.moves.clear();self.bytes=0
        return values


class FriendsWorld:
    def __init__(self):
        self.towns={};self.members={};self.parties={};self.party_of={}
        self.invitations={};self.next_party=900001
        self.recruitment_candidates={};self.recruitment_cleanup_errors=deque(maxlen=32)
        from els_server.domain.friends_dungeon import FriendsDungeons
        self.dungeons=FriendsDungeons(self)
        from els_server.domain.field_boss import FieldBosses
        self.field_bosses=FieldBosses(self)

    def disconnect(self,session):
        try:
            self.field_bosses.detach(session)
        finally:
            try:
                self.leave(session)
            finally:
                try:
                    self.leave_party(session)
                finally:
                    self.invitations={s:v for s,v in self.invitations.items() if s is not session and v['inviter'] is not session}

    def party_snapshot(self,party,reset=False):
        from els_server.domain.normal_party import roster_events
        notices=roster_events(party,reset=reset)
        for member in list(party['members']):
            for notice in notices:self.send(member,notice)

    def leave_party(self,session):
        from els_server.domain.party_recruitment import invalidate
        invalidate(self,session)
        current=self.party_of.get(session)
        try:
            if current and (current.get('challenge') or current.get('challenge_pending')):
                from els_server.domain.group_challenge import cancel
                cancel(self,current)
        finally:
            try:
                self.dungeons.detach(session)
            finally:
                from els_server.domain.party_recruitment import leave as leave_recruitment
                handled=leave_recruitment(self,session,forced=True)
                if not handled:
                    party=self.party_of.pop(session,None)
                    if party is not None:
                        party['members'].remove(session);party['ready'].discard(session)
                        from els_server.domain.normal_party import ordinary
                        if ordinary(party):party['ready'].clear();party.pop('admission',None)
                        self.send(session,wire.party_removed(session.account.uid))
                        if len(party['members'])<2:
                            for other in list(party['members']):
                                self.party_of.pop(other,None);self.send(other,wire.party_removed(session.account.uid))
                            self.parties.pop(party['id'],None)
                        else:
                            if party['leader'] is session:party['leader']=party['members'][0]
                            self.party_snapshot(party,reset=True)

    def party_request(self,session,event):
        from els_server.domain import party_recruitment
        result=party_recruitment.handle(self,session,event)
        if result is not None:return result
        kind=event.kind
        if event.event_id==0x202 and self.party_of.get(session,{}).get('recruitment'):
            if kind==0x13f:
                if len(event.payload)!=4:return []
                return party_recruitment.leave(self,session)
            if kind==0x145:return party_recruitment.select(self,session,event)
        if event.event_id==0x202 and kind in (0x14e,0x151):
            from els_server.domain.party_commands import handle
            return handle(self,session,event)
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
            try:
                request=wire.party_invite_request(event.payload,settings=True)
                uid,name,requested=(request[k] for k in ('uid','name','dungeon'))
            except (ValueError,UnicodeError):return [wire.party_invite_ack(result=-1)]
            target=next((s for s in self.members if s.account.character()['name']==name and uid in (0,s.account.uid)),None)
            party=self.party_of.get(session)
            from els_server.domain.raid_party import raid_definition,capacity
            raid=raid_definition(requested)
            if raid and party is not None and party.get('recruitment'):return [wire.party_invite_ack(result=-1)]
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
            ordinary_selection=None
            if not raid and not (party and party.get('raid_party')):
                from els_server.domain.normal_party import invite_selection
                ordinary_selection=invite_selection(self,session,target,party,request)
                if ordinary_selection is None:return [wire.party_invite_ack(result=-1)]
            session.invite_times.append(now)
            self.invitations[target]={'inviter':session,'expires':now+30,'party':party,'raid_dungeon':requested if raid else None,'ordinary_selection':ordinary_selection}
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
            if not accepted:
                self.invitations.pop(session);return [wire.party_answer_ack(inviter.account.uid)]
            if invite.get('ordinary_selection') is not None:
                from els_server.domain.normal_party import accept
                return accept(self,session,invite)
            self.invitations.pop(session)
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
            if ready!=(session in party['ready']):party.pop('admission',None)
            if ready:party['ready'].add(session)
            else:party['ready'].discard(session)
            for other in party['members']:self.send(other,wire.party_ready_notice(session.account.uid,ready))
            return []

    def room(self,session):return self.towns.get(self.members.get(session),{})

    def send(self,session,message,move_uid=None):
        if session.released or getattr(session,'social_overflow',False):return
        try:session.mailbox.append(message,move_uid)
        except SessionOrderError:session.social_overflow=True

    def leave(self,session):
        from els_server.domain.party_recruitment import invalidate
        invalidate(self,session)
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
        from els_server.domain.character_custom import restored as custom_restored
        for other,(character,_,_) in room.items():
            # Match the actor already added above; use a fresh authoritative
            # role/title projection rather than a cached expired title.
            current=other.account.character()
            if current['uid']==character['uid']:
                for event in custom_restored(current):self.send(session,event)
        notice=wire.town_members(added=[own])
        own_custom=custom_restored(own[0])
        for other in list(room):
            self.send(other,notice)
            for event in own_custom:self.send(other,event)
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
        from els_server.domain.character_custom import restored as custom_restored
        custom=custom_restored(current[0])
        for other in list(room):
            if other is not session:
                self.send(other,notice)
                for event in custom:self.send(other,event)

    def custom_changed(self,session,messages):
        from els_server.domain.character_custom import admitted
        room=self.room(session)
        if not admitted(session) or session not in room or room[session][0]['uid']!=session.account.uid:return
        current=(session.account.character(),session.account.get_location(),session.account.get_inventory_snapshot()['items'])
        notices=[e for e in messages if e.event_id==0x201 and e.kind==0x18e and len(e.payload)>=16 and int.from_bytes(e.payload[:8],'big')==session.account.uid]
        if not notices:return
        room[session]=current
        for other in list(room):
            if other is not session and other.role=='game' and other.phase=='town_ready' and other.active_map==session.active_map:
                for event in notices:self.send(other,event)

    def chat(self,session,event):
        if session.phase not in ('town_ready','dungeon_active') or session.role!='game':return [wire.chat_ack(-1)]
        now=time.monotonic()
        while session.chat_times and now-session.chat_times[0]>=5:session.chat_times.popleft()
        if len(session.chat_times)>=5:return [wire.chat_ack(-1)]
        try:
            request=wire.chat_request(event.payload,details=True)
            channel,text=request['channel'],request['text']
        except (ValueError,UnicodeError):return [wire.chat_ack(-1)]
        if channel==4:
            from els_server.domain.whisper import handle
            return handle(self,session,request,now)
        if channel==0 and session.phase=='dungeon_active':
            from els_server.domain.dungeon_chat import handle
            return handle(self,session,text,now)
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
