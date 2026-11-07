"""Native Town/GuildAgit invitation consent and shared ordinary1v1 admission."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import json,math,secrets,sqlite3,struct,time,uuid
from els_server.domain import pvp_actor,guild_agit_flow
from els_server.domain.pvp_registration import Ticket,_binding,_same,_envelope
from els_server.domain.pvp_loading import _inventory_signature
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import duel_messages as wire,social_messages,guild_agit_messages
from els_server.storage.item_actor import require_active_character


@dataclass(frozen=True)
class Origin:
    session: object
    binding: tuple
    scene: tuple
    context: object
    saved_location: str

    def matches(self,other):
        return(self.session is other.session and self.scene==other.scene
            and self.context is other.context and self.saved_location==other.saved_location
            and _same(self.session,self.binding))


@dataclass(eq=False)
class Invitation:
    identity: int
    generation: str
    members: tuple
    origins: tuple
    full_user: bytes
    excluded: frozenset


class Duels:
    def __init__(self,pvp):
        self.pvp=pvp;self.world=pvp.world;self.pending={};self.returning={};self.positions={}

    def source(self,s):
        self.retire_town_return(s)
        guard=pvp_actor.capture(self.world,s)
        if(not s.enter_town or s.dungeon_return_pending or self.pvp.room(s)is not None
           or self.world.dungeons.transport_room(s)is not None or s in self.world.party_of
           or getattr(s,'town_warp_transition',None)is not None
           or getattr(s,'housing_own_room',None)is not None
           or s in self.world.player_trades.by_session):
            raise ValueError('Duel current unoccupied native actor required')
        location=s.account.get_location();context=getattr(s,'guild_agit',None)
        if s.phase=='town_ready':
            from els_server.storage.local_state import TOWN_SCENES
            key=(1,location['map']);entry=self.world.towns.get(key,{}).get(s)
            if(context is not None or location['map']not in TOWN_SCENES
               or s.active_map!=location['map']or s.pending_map!=location['map']
               or not{0x225,0x227}.issubset(s.completed)
               or self.world.members.get(s)!=key or entry is None
               or entry[0]['uid']!=s.account.uid):raise ValueError('Duel actual source Town required')
            scene=('town',location['map']);guild_guard=None
        elif s.phase=='guild_agit_ready'and context is not None and not context.get('revoked'):
            _,guild_guard=guild_agit_flow.bank_capture(s);scene=('guild',context['guild'])
        else:raise ValueError('Duel actual Town/GuildAgit readiness required')
        origin=Origin(s,_binding(s),scene,context,json.dumps(location,sort_keys=True))
        def check(db):
            guard()
            if getattr(s,'guild_agit',None)is not context:raise ValueError('Duel source instance changed')
            require_active_character(db,s.account.uid)
            if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(s.account.uid,)).fetchone()!=(s.account.account_id,):
                raise ValueError('Duel saved owner changed')
            if guild_guard is not None:guild_guard(db)
        return origin,check

    def sources(self,invitation,db):
        current=[];checks=[]
        for s,old in zip(invitation.members,invitation.origins):
            origin,check=self.source(s)
            if not old.matches(origin):raise ValueError('Duel invitation source retired')
            current.append(origin);checks.append(check);check(db)
        if any(self.pending.get(s)is not invitation for s in invitation.members):
            raise ValueError('Duel invitation generation changed')
        return tuple(current),tuple(checks)

    def forget(self,invitation):
        for s in invitation.members:
            if self.pending.get(s)is invitation:self.pending.pop(s)

    def invite(self,s,event):
        request=wire.invitation_request(event.payload)
        if request['sender']!=s.account.uid or request['name']!=s.account.character()['name']:
            raise ValueError('Duel inviter original identity')
        target=next((p for p in s.application.playing.values()if p.account.uid==request['target']),None)
        if target is None or target is s or target.account.account_id==s.account.account_id:
            return [wire.requested(request['target'],1678)]
        if any(p in self.pending for p in(s,target)):return [wire.requested(request['target'],1682)]
        reg=self.pvp.registrations
        if any(p in reg.queue or p in reg.offers for p in(s,target)):
            return [wire.requested(request['target'],1681)]
        origins=[];checks=[]
        for p in(s,target):
            origin,check=self.source(p);origins.append(origin);checks.append(check)
        if(origins[0].scene!=origins[1].scene
           or Path(s.account.store.path).resolve()!=Path(target.account.store.path).resolve()):
            raise ValueError('Duel same visible source instance required')
        path=Path(s.account.store.path).resolve()
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))as db:
            db.execute('BEGIN')
            for check in checks:check(db)
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='native_duel_refusals'AND type='table'").fetchone():
                until=db.execute('SELECT until FROM native_duel_refusals WHERE inviter=?AND recipient=?',
                    (s.account.uid,target.account.uid)).fetchone()
                if until is not None and until[0]>int(time.time()):return [wire.requested(target.account.uid,1680)]
        # End the source reader before FullUser's independent legacy repair writer.
        from els_server.protocol.dungeon_messages import member
        full=member(s.account.get_skills(),s.account.character(),s.account.get_inventory_snapshot()['items'],
            account_id=s.account.account_id,peer_port=21100)
        notice=wire.invited(s.account.uid,target.account.uid,request['first_hint'],request['second_hint'],
            s.account.character()['name'],full,request['excluded'],request['flag'])
        response=[wire.requested(target.account.uid)]
        boxes=_prepared_boxes([(target,(notice,))],response)
        invitation=Invitation(secrets.randbelow(2**63-1)+1,str(uuid.uuid4()),(s,target),tuple(origins),full,request['excluded'])
        # Recheck the original actors and prepared mailboxes before publication.
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10))as db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            for check in checks:check(db)
            if any(p in self.pending or p in reg.queue or p in reg.offers for p in(s,target)):
                raise ValueError('Duel late competing invitation/matching')
            # The successful application is the fact, independently of its
            # later acceptance or battle. Reuse the server-source journal.
            from els_server.storage import achievements as achievement_state
            achievement_state.ensure(db)
            operation='duel-invite:'+invitation.generation
            digest,_=achievement_state._operation(db,s.account.account_id,s.account.uid,'duel-invite',
                dict(request=event.payload.hex(),scene=origins[0].scene),operation)
            achievement_state._save(db,s.account.account_id,s.account.uid,'duel-invite',digest,operation,
                dict(target=target.account.uid,scene=origins[0].scene,created_at=int(time.time())))
            for check in checks:check(db)
            db.commit()
        for p in(s,target):self.pending[p]=invitation
        for p,box in boxes.items():p.mailbox=box
        return response

    def answer(self,s,event):
        invitation=self.pending.get(s)
        if invitation is None or invitation.members[1]is not s:raise ValueError('Duel current recipient required')
        inviter,recipient=invitation.members
        request=wire.answer_request(event.payload,inviter=inviter.account.uid,
            recipient=recipient.account.uid,full_user=invitation.full_user)
        path=Path(s.account.store.path).resolve();decision=request['decision']
        with closing(sqlite3.connect(path,timeout=10))as db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE'if decision==1 else'BEGIN')
            origins,checks=self.sources(invitation,db)
            if decision:
                boxes=_prepared_boxes([(inviter,(wire.declined(recipient.account.uid,1679 if decision==1 else 1678),))],())
                if decision==1:
                    db.execute('CREATE TABLE IF NOT EXISTS native_duel_refusals(inviter INTEGER NOT NULL REFERENCES characters(uid)ON DELETE CASCADE,recipient INTEGER NOT NULL REFERENCES characters(uid)ON DELETE CASCADE,generation TEXT NOT NULL,until INTEGER NOT NULL,PRIMARY KEY(inviter,recipient))')
                    db.execute('INSERT INTO native_duel_refusals VALUES(?,?,?,?) ON CONFLICT(inviter,recipient)DO UPDATE SET generation=excluded.generation,until=excluded.until',
                        (inviter.account.uid,recipient.account.uid,invitation.generation,int(time.time())+600))
                for check in checks:check(db)
                db.commit();self.forget(invitation)
                for p,box in boxes.items():p.mailbox=box
                return []
            if not invitation.excluded.issubset(request['excluded']):raise ValueError('Duel recipient changed inviter exclusions')
            if not all(self.pvp.support_ready(p)for p in invitation.members):raise ValueError('Duel current native HP support required')
            tickets=tuple(Ticket(p,invitation.generation,_binding(p),invitation.generation,None,time.monotonic())for p in invitation.members)
            room,admission=self.pvp.loading.prepare(invitation.members,tickets,invitation.identity,
                invitation.generation,request['excluded'],s.port_probe_port,kind='challenge',origins=origins)
            deliveries=[(p,(admission,))for p in invitation.members];peer_checks=[]
            if origins[0].scene[0]=='town':
                key=self.world.members[inviter]
                notice=social_messages.town_members(removed=[p.account.uid for p in invitation.members])
                for other in self.world.towns[key]:
                    if other not in invitation.members:
                        peer_checks.append(pvp_actor.capture(self.world,other));deliveries.append((other,(notice,)))
            else:
                for other,same,check in guild_agit_flow._peers(inviter,origins[0].scene[1]):
                    if other not in invitation.members:
                        peer_checks.append(lambda check=check:check(db))
                        deliveries.append((other,tuple(guild_agit_messages.removed(p.account.uid)for p in invitation.members)))
            boxes=_prepared_boxes(deliveries,())
            for check in checks:check(db)
            for check in peer_checks:check()
            if any(self.pending.get(p)is not invitation or self.pvp.room(p)is not None for p in invitation.members):
                raise ValueError('Duel late admission generation changed')
            if tuple(_inventory_signature(p)for p in invitation.members)!=room.signatures:
                raise ValueError('Duel native member source changed')
            for check in checks:check(db)
            for check in peer_checks:check()
            db.rollback()
            if origins[0].scene[0]=='town':
                key=self.world.members[inviter];old=self.world.towns[key]
                for p in invitation.members:self.world.members.pop(p);old.pop(p)
                if not old:self.world.towns.pop(key)
            else:
                for p in invitation.members:p.guild_agit=None
            self.forget(invitation)
            for p in invitation.members:
                self.pvp.registrations.gates.pop(p,None);self.returning.pop(p,None)
                self.pvp.loading.rooms[p]=room;p.phase='pvp_loading';p.active_map=p.pending_map=room.map_id
            for p,box in boxes.items():p.mailbox=box
            return []

    def cancel(self,s,event):
        wire.cancel_request(event.payload)
        invitation=self.pending.get(s)
        if invitation is None:return []
        other=next(p for p in invitation.members if p is not s)
        boxes=_prepared_boxes([(other,(wire.declined(s.account.uid,1678),))]if not other.released else[],())
        self.forget(invitation)
        for p,box in boxes.items():p.mailbox=box
        return []

    def request(self,s,event,sequence):
        if event.kind not in(0x5c6,0x5c9,0x5cb):return None
        reply_guard=pvp_actor.safe_capture(self.world,s)
        if reply_guard is None:return []
        try:
            if not _envelope(event)or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Duel original envelope/sequence')
            self.periodic(s)
            return self.invite(s,event)if event.kind==0x5c6 else self.answer(s,event)if event.kind==0x5c9 else self.cancel(s,event)
        except(ValueError,sqlite3.Error):
            if event.kind==0x5cb:return []
            target=0
            if event.kind==0x5c6 and len(event.payload)>=24:target=struct.unpack_from('>Q',event.payload,12)[0]
            elif event.kind==0x5c9 and len(event.payload)>=16:target=struct.unpack_from('>Q',event.payload)[0]
            answer=lambda:[wire.requested(target,1678)]if event.kind==0x5c6 else[wire.declined(target,1678)]
            invitation=self.pending.get(s)
            if(event.kind==0x5c9 and invitation is not None and invitation.members[1]is s
               and len(event.payload)>=16 and struct.unpack_from('>QQ',event.payload)==tuple(p.account.uid for p in invitation.members)):
                response=pvp_actor.failed(reply_guard,answer)
                if not response:return []
                other=invitation.members[0];other_guard=pvp_actor.safe_capture(self.world,other)
                if other_guard is None:self.forget(invitation);return response
                boxes=_prepared_boxes([(other,(wire.declined(s.account.uid,1678),))],response)
                reply_guard();other_guard();self.forget(invitation)
                for p,box in boxes.items():p.mailbox=box
                return response
            return pvp_actor.failed(reply_guard,answer)

    def periodic(self,s):
        self.retire_town_return(s)
        invitation=self.pending.get(s)
        if invitation is None:return
        try:
            for p,old in zip(invitation.members,invitation.origins):
                current,_=self.source(p)
                if not old.matches(current):raise ValueError('Duel source left')
        except ValueError:self.disconnect(s)

    def disconnect(self,s):
        invitation=self.pending.get(s)
        if invitation is not None:
            self.forget(invitation)
            for other in invitation.members:
                if other is not s and not other.released:self.world.send(other,wire.declined(s.account.uid,1678))
        self.returning.pop(s,None)
        for key in tuple(self.positions):
            if key[1]is s:self.positions.pop(key)

    def finished(self,s,room):
        if room.kind!='challenge':return
        origin=room.origins[room.members.index(s)]
        if origin.scene[0]=='guild':self.returning[s]=(room.seed,origin)
        self.positions.pop((room.seed,s),None)

    def return_source(self,s):
        current=self.returning.get(s)
        if current is None:return None
        _,origin=current
        pvp_actor.actor(self.world,s)
        if(not _same(s,origin.binding)or origin.scene[0]!='guild'
           or s.phase!='map_loading'or not s.dungeon_return_pending or s.pending_map is not None
           or self.pvp.room(s)is not None or self.world.dungeons.room(s)is not None
           or s in self.world.members or s in self.world.party_of
           or getattr(s,'guild_agit',None)is not None
           or json.dumps(s.account.get_location(),sort_keys=True)!=origin.saved_location):
            raise ValueError('Duel exact completed GuildAgit return required')
        return origin

    def retire_town_return(self,s):
        current=self.returning.get(s)
        if current is None or s.phase!='town_ready':return
        _,origin=current
        pvp_actor.actor(self.world,s)
        location=s.account.get_location();key=(1,location['map'])
        entry=self.world.towns.get(key,{}).get(s)
        saved=json.loads(origin.saved_location)
        if(not _same(s,origin.binding)or s.dungeon_return_pending
           or s.active_map!=location['map']or s.pending_map!=location['map']
           or location['map']!=saved['map']or not{0x225,0x227}.issubset(s.completed)
           or self.world.members.get(s)!=key or entry is None or entry[0]['uid']!=s.account.uid
           or self.pvp.room(s)is not None or self.world.dungeons.room(s)is not None
           or getattr(s,'guild_agit',None)is not None):
            raise ValueError('Duel completed Town return source changed')
        self.returning.pop(s)

    def position(self,s,event):
        room=self.pvp.room(s)
        if(room is None or room.kind!='challenge'or room.origins[room.members.index(s)].scene[0]!='guild'
           or room.phase!='loading'or not _envelope(event)or len(event.payload)!=12):
            raise ValueError('Duel original GuildAgit transition position')
        for p in room.members:self.pvp.loading.current(p,room)
        xyz=struct.unpack('>fff',event.payload)
        if any(not math.isfinite(v)or abs(v)>1000000 for v in xyz):raise ValueError('Duel finite native origin position')
        key=(room.seed,s);previous=self.positions.get(key)
        if previous is not None and previous!=event.payload:raise ValueError('Duel changed origin position retry')
        # Retain only the bound hint until actual native return qualification.
        # It never becomes an ordinary saved Town coordinate.
        self.positions[key]=bytes(event.payload)
        return []
