"""Shared admission and lifecycle, with per-character durable rewards.

Only Application's serialized worker calls this module. Combat reports come
from the authenticated room master; this is a friends prototype, not a server
damage simulator. Native action transport/GUI acceptance is a separate gate.
"""
import math,struct,time,uuid
from dataclasses import dataclass,field
from els_server.domain.local_session import LocalSession,SessionOrderError
from els_server.domain.raid_economy_flow import managed as raid_economy_managed
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32,wstring


@dataclass(eq=False)
class Room:
    party:dict
    members:tuple
    leader:object
    identity:int
    seed:str
    progress:dict=field(default_factory=dict)
    loaded:set=field(default_factory=set)
    ended:set=field(default_factory=set)
    portals:set=field(default_factory=set)
    phase:str='loading'
    deadline:float=0
    previous_part:int|None=None
    last_poll:float=0


class FriendsDungeons:
    def __init__(self,world):self.world=world;self.rooms={}

    def send(self,session,messages):
        for message in messages:self.world.send(session,message)

    def room(self,session):return self.rooms.get(session)

    def transport_room(self,session):return self.room(session) or self.world.field_bosses.room(session)

    def _current_transport_member(self,application,s,r):
        from els_server.domain.equipment_chip_flow import current_lease
        if (s is None or getattr(s,'application',None) is not application
            or application.world is not self.world or s not in r.members
            or self.transport_room(s) is not r or not current_lease(s)
            or s.coop_error or not application.registry.enabled(s.account.account_id)):
            return False
        if self.room(s) is r:
            return bool(s.phase in ('dungeon_loading','dungeon_active')
                and r.party.get('run') is r and self.world.party_of.get(s) is r.party
                and s in r.party['members'])
        return s.phase=='field_active'

    def _current_transport_roster(self,application,r):
        # A completed room retains its original peer ports until the last
        # result-scene member leaves. Departed members cannot send/receive,
        # but must not revoke the remaining members' existing native route.
        return all(self._current_transport_member(application,m,r)
            for m in r.members if r.phase!='clear' or self.transport_room(m) is r)

    def manifest(self,application,account_id):
        if not application.registry.enabled(account_id):raise SessionOrderError('Account disabled')
        s=application.playing.get(account_id);r=self.transport_room(s)
        if r is None:
            # A solo run still performs the original native relay6/7 bootstrap.
            # No peer proxy/route is created: relay_target continues to reject
            # every target outside an admitted shared room.
            if (s is None or s.released or s.coop_error or s.role!='game'
                or s.phase not in ('dungeon_loading','dungeon_active')
                or not s.enter_dungeon or s.dungeon_return_pending
                or s in self.world.party_of or s.account.account_id!=account_id
                or s.identity['id']!=account_id
                or getattr(s,'dungeon_participants',None)!=frozenset((s.account.uid,))):return None
            try:
                epoch=uuid.UUID(s.reward_run_id)
            except (ValueError,TypeError,AttributeError):return None
            if epoch.version!=4 or str(epoch)!=s.reward_run_id:return None
            return dict(epoch=str(epoch),uid=s.account.uid,peers=[dict(uid=s.account.uid,port=21100)])
        if len(r.members)<2 or r.phase=='failed':return None
        if not self._current_transport_member(application,s,r) or not self._current_transport_roster(application,r):return None
        return dict(epoch=r.seed,uid=s.account.uid,peers=[dict(uid=m.account.uid,port=21100+i) for i,m in enumerate(r.members)])

    def relay_target(self,application,account_id,epoch,target):
        if not application.registry.enabled(account_id):raise SessionOrderError('Account disabled')
        s=application.playing.get(account_id);r=self.transport_room(s)
        if r is None or r.phase=='failed' or r.seed!=epoch or s.released or s.coop_error:return None
        if not self._current_transport_member(application,s,r) or not self._current_transport_roster(application,r):return None
        other=next((m for m in r.members if m.account.uid==target and m is not s),None)
        if other is None or not self._current_transport_member(application,other,r):return None
        if not application.registry.enabled(other.identity['id']):return None
        return other.identity['id'],s.account.uid

    def relay_lost(self,application,account_id):
        s=application.playing.get(account_id);r=self.room(s)
        if r is not None and r.phase!='clear':self.abort(r,'Party dungeon aborted: combat relay disconnected')
        r=self.world.field_bosses.room(s)
        if r is not None and r.phase not in ('clear','failed'):self.world.field_bosses.abort(r,'combat relay disconnected')

    def abort(self,room,reason,leaving=None):
        room.party['run']=None;room.party['ready'].clear()
        for s in room.members:
            self.rooms.pop(s,None)
            s.dungeon_participants=frozenset((s.account.uid,))
            if s is not leaving and not s.released:s.coop_error=reason

    def detach(self,session):
        room=self.room(session)
        if room is None:return
        if not all(s.clear_notified for s in room.members):
            self.abort(room,'Party dungeon aborted: member left',leaving=session)
        else:
            self.rooms.pop(session,None)
            session.dungeon_participants=frozenset((session.account.uid,))
            if not any(self.room(s) is room for s in room.members):
                room.party['run']=None;room.party['ready'].clear()

    def admissible(self,party,leader,identity):
        if identity in (35100,35360):
            from els_server.domain.native_ticket_rules import enabled as ticket_enabled
            if not ticket_enabled():return False
        if identity in (34530,34540):
            from els_server.domain.aurora_ticket_rules import enabled as aurora_enabled
            if not aurora_enabled():return False
        if party.get('recruitment'):
            from els_server.domain.party_recruitment import waiting
            try:waiting(self.world,party)
            except ValueError:return False
        from els_server.domain.dungeon_routes import route_catalog
        from els_server.domain.region_quests import account_dungeon_allowed
        from els_server.domain.raid_party import admission_size,raid_definition
        from els_server.domain.normal_fatigue_flow import admission as fatigue_admission
        selected=route_catalog().entry_identity(party['dungeon'])
        ordinary=not party.get('raid_party') and not party.get('challenge')
        return ((identity==selected or party.get('challenge'))
            and (not ordinary or raid_definition(identity) is None)
            and party['leader'] is leader and party['run'] is None and not party.get('challenge_pending') and admission_size(party,identity)
            and (identity==30000 or route_catalog().supports(identity,internal=bool(party.get('challenge'))))
            and all(s.phase=='town_ready' and s in self.world.members and not s.released
                and (s is leader or s in party['ready']) and account_dungeon_allowed(s.account,identity) and fatigue_admission(s,identity)
                for s in party['members']))

    def request(self,s,event,request_sequence=None):
        if event.event_id!=0x202:return None
        party=self.world.party_of.get(s);room=self.room(s);kind=event.kind
        if party is not None and party.get('solo_challenge'):return None
        if room is None:
            if party is None or kind not in (0x7d4,0x382):return None
            if kind==0x7d4:
                mode,identity=struct.unpack('>ii',event.payload) if len(event.payload)==8 else (0,0)
                from els_server.domain.dungeon_routes import route_catalog
                from els_server.protocol.dungeon_errors import ENTRY_REQUIREMENTS_NOT_MET,INVALID_DUNGEON_MODE
                identity=route_catalog().entry_identity(identity)
                valid=(s.application.config.friends_coop_enabled and mode in (1,2) and self.admissible(party,s,identity))
                if valid:
                    from els_server.domain.party_commands import selection_context
                    party['admission']=(identity,time.monotonic()+30,tuple(party['members']),selection_context(party))
                elif party['leader'] is s:party.pop('admission',None)
                return [Event(0x201,kind=0x7d5,payload=i32(0 if valid else ENTRY_REQUIREMENTS_NOT_MET if mode in (1,2) else INVALID_DUNGEON_MODE)+i32(1))]
            admission=party.get('admission');payload=event.payload
            from els_server.domain.party_commands import selection_context
            from els_server.domain.dungeon_routes import route_catalog
            identity=route_catalog().entry_identity(party['dungeon'])
            # An already consented challenge selects its qualified current node
            # through the existing preflight, not the ordinary room-map setting.
            if party.get('challenge') and admission is not None:identity=admission[0]
            # Current original2D6D830 sends382 for an existing party; it does
            # not require the solo/experimental7D4 preflight. The server's
            # selected map and current ready roster remain authoritative.
            native_normal=(admission is None and not any(party.get(k)
                for k in ('raid_party','challenge','challenge_pending','solo_challenge'))
                and party.get('difficulty',0)==0 and party.get('mode',0)==0)
            preflight=(admission is not None and len(admission)==4
                and admission[0]==identity and admission[1]>=time.monotonic()
                and tuple(party['members'])==admission[2]
                and selection_context(party)==admission[3])
            valid=(s.application.config.friends_coop_enabled and (native_normal or preflight)
                and event.payload_mode==0 and self.admissible(party,s,identity)
                and 23<=len(payload)<=86 and any(struct.unpack_from('>I',payload,o)[0]==len(payload)-22 for o in range(19)))
            if not valid:return [Event(0x201,kind=0x383,payload=i32(-1)+wstring('')*2)]
            if identity in (35100,35360,34530,34540):
                if identity in (34530,34540):
                    from els_server.domain.aurora_group_admission import start as start_aurora
                    admitted=start_aurora(self,party,s,identity,event)
                else:admitted=self.start_native_tickets(party,s,identity,event)
                if not admitted:
                    return [Event(0x201,kind=0x383,payload=i32(-1)+wstring('')*2)]
            else:
                self.start(party,s,identity,event)
            return [Event(0x201,kind=0x383,payload=bytes(4)+wstring('')*2)]
        if kind in (0x7d4,0x382):return []
        if kind==0x2ce:
            from els_server.domain.friends_spawns import spawn
            return spawn(self,room,s,event,request_sequence)
        if kind==0x91:return self.progress(room,s,event)
        if kind==0xb3:return self.loaded(room,s,event)
        if kind==0xad:return self.death(room,s,event)
        if kind==0xb8:return self.portal(room,s,event)
        if kind==0xbb:return self.end_part(room,s,event)
        # Local exit/return handling runs afterwards. An unfinished party run
        # aborts for everyone instead of silently producing separate worlds.
        if kind==0x67:
            if not (100<=len(event.payload)<=8192 and event.payload[:4]==i32(0x72)):return []
            self.detach(s)
        if kind==0x225:
            if not s.clear_notified:return []
            if event.payload!=i32(s.account.get_location()['map'])+b'\0':return []
            self.detach(s)
        return None

    def start(self,party,leader,identity,event):
        from els_server.protocol.dungeon_messages import party_dungeon_start
        from els_server.domain.dungeon_routes import DungeonRun
        members=tuple(party['members']);seed=str(uuid.uuid4())
        from els_server.domain.normal_fatigue_flow import admission as fatigue_admission
        if not all(fatigue_admission(s,identity)for s in members):raise SessionOrderError('A party member has no ordinary fatigue')
        # Compile the roster and source route before changing any session.
        admitted_members={}
        packet=party_dungeon_start(members,leader,identity,party['id'],bootstrap_port=leader.port_probe_port,member_captures=admitted_members)
        runs={s:DungeonRun(identity,seed,internal=bool(party.get('challenge'))) if identity!=30000 else None for s in members}
        participants=frozenset(s.account.uid for s in members)
        room=Room(party,members,leader,identity,seed,deadline=time.monotonic()+90)
        for s in members:
            s.dungeon_requested=True;s.requested_dungeon_id=identity;s.requested_dungeon_mode=1
            if party.get('challenge'):
                from els_server.domain.challenge_flow import allowed
                s.requested_challenge=allowed(s,identity)
            result=LocalSession.handle(s,event)
            if not any(e.kind==0x14a for e in result):raise SessionOrderError('Party admission changed during serialized start')
            # LocalSession's solo preparation is discarded for a shared run.
            # Retain this actor's exact admitted party member for later expiry.
            s._capture_luciel_dungeon_hp(*admitted_members[s])
            s.dungeon_run=runs[s]
            s.reward_run_id=str(uuid.uuid5(uuid.UUID(seed),'reward:'+str(s.account.uid))) if s.reward_test else None
            s.dungeon_participants=participants
            from els_server.domain.pve_economy_flow import bind_story
            bind_story(s)
            from els_server.domain.normal_fatigue_flow import bind as bind_normal_fatigue
            bind_normal_fatigue(s,epoch=seed)
            self.rooms[s]=room
            self.world.synchronize(s)
            self.send(s,[packet])
            if party.get('challenge'):
                from els_server.domain.challenge_flow import notification
                self.send(s,[notification(s)])
        from els_server.domain.friends_spawns import capture_static_origin
        capture_static_origin(room)
        party.pop('admission',None);party['run']=room;party['dungeon']=identity

    def start_native_tickets(self,party,leader,identity,event):
        """One original ready-roster entry, one SQLite debit for every member."""
        import json,sqlite3
        from pathlib import Path
        from els_server.protocol.protocol_codec import encode_event
        from els_server.protocol.dungeon_messages import party_dungeon_start
        from els_server.domain.dungeon_routes import DungeonRun
        from els_server.domain.native_ticket_admission import _delta
        from els_server.storage.native_dungeon_tickets import admit_group
        from els_server.domain.equipment_chip_flow import current_lease
        members=tuple(party['members'])
        if (party['leader'] is not leader or len(members)<2 or len(set(members))!=len(members)
            or any(not s.item_test or s.account.store is None for s in members)):
            return False
        paths={Path(s.account.store.path).resolve() for s in members}
        if len(paths)!=1:return False
        path=paths.pop();actors=tuple((s.account.account_id,s.account.uid) for s in members)
        selection=(tuple(members),frozenset(party['ready']),party.get('dungeon'),party.get('run'))
        seed=str(uuid.uuid4());snapshots={s:dict(s.__dict__) for s in members}
        runs={s:DungeonRun(identity,seed,internal=False) for s in members}
        participants=frozenset(s.account.uid for s in members)
        room=Room(party,members,leader,identity,seed,deadline=time.monotonic()+90)
        prepared={}

        def guard():
            if (selection!=(tuple(party['members']),frozenset(party['ready']),party.get('dungeon'),party.get('run'))
                or not self.admissible(party,leader,identity)
                or any(not current_lease(s) or s.account.store is None
                    or Path(s.account.store.path).resolve()!=path for s in members)):
                raise ValueError('Permanent ticket party readiness/lease changed')

        def encode(chosen,after):
            inventories={};deltas={}
            for s,item,remaining in zip(members,chosen,after):
                inventory=[dict(value) for value in s.account.get_inventory_snapshot()['items']]
                positions=[i for i,value in enumerate(inventory) if value['uid']==item['uid']]
                if (len(positions)!=1 or inventory[positions[0]]['template']!=item['template']
                    or inventory[positions[0]]['count']!=item['count']):
                    raise ValueError('Permanent ticket party inventory changed')
                index=positions[0]
                if remaining is None:del inventory[index]
                else:inventory[index]['count']=remaining['count']
                inventories[s]=inventory;deltas[s]=_delta(item,remaining)
            captured={}
            packet=party_dungeon_start(members,leader,identity,party['id'],
                bootstrap_port=leader.port_probe_port,member_captures=captured,inventories=inventories)
            ack=Event(0x201,kind=0x383,payload=bytes(4)+wstring('')*2)
            for event_to_encode in [packet,ack,*deltas.values()]:encode_event(event_to_encode)
            for s in members:
                s._native_group_ticket_prepare=True
                s.dungeon_requested=True;s.requested_dungeon_id=identity;s.requested_dungeon_mode=1
                result=LocalSession.handle(s,event)
                if not any(reply.kind==0x14a for reply in result):
                    raise ValueError('Permanent ticket party member admission changed')
                s._capture_luciel_dungeon_hp(*captured[s])
                s.dungeon_run=runs[s]
                s.reward_run_id=str(uuid.uuid5(uuid.UUID(seed),'reward:'+str(s.account.uid))) if s.reward_test else None
                s.dungeon_participants=participants
                from els_server.domain.pve_economy_flow import bind_story
                bind_story(s)
                from els_server.domain.normal_fatigue_flow import bind as bind_normal_fatigue
                bind_normal_fatigue(s,epoch=seed)
                del s._native_group_ticket_prepare
            prepared.update(packet=packet,deltas=deltas)
            return json.dumps(dict(packet=packet.payload.hex(),
                deltas={str(s.account.uid):deltas[s].payload.hex() for s in members}),
                separators=(',',':')).encode()

        try:
            admit_group(path,actors,identity,seed,event.payload,encode,guard)
        except Exception:
            for s,snapshot in snapshots.items():s.__dict__.clear();s.__dict__.update(snapshot)
            return False
        for s in members:
            self.rooms[s]=room
            self.world.synchronize(s)
            self.send(s,[prepared['deltas'][s],prepared['packet']])
        from els_server.domain.friends_spawns import capture_static_origin
        capture_static_origin(room)
        party.pop('admission',None);party['run']=room;party['dungeon']=identity
        return True

    def progress(self,r,s,event):
        if len(event.payload)!=8:return []
        value,mode=struct.unpack('>ii',event.payload)
        if not 0<=value<=100 or mode!=0 or r.phase not in ('loading','substage','active'):return []
        if value<r.progress.get(s,0):return []
        r.progress[s]=value
        for other in r.members:self.send(other,[Event(0x201,kind=0x93,payload=struct.pack('>Qi',s.account.uid,value))])
        if r.phase=='loading' and all(r.progress.get(m)==100 for m in r.members):
            for other in r.members:
                messages=LocalSession.handle(other,Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))
                self.send(other,[e for e in messages if e.kind not in (0x92,0x93)])
            r.phase='substage';r.deadline=time.monotonic()+60
        return [Event(0x201,kind=0x92,payload=struct.pack('>iiI',0,value,0))]

    def loaded(self,r,s,event):
        if len(event.payload)!=9 or event.payload[:5]!=bytes(5):return []
        value=struct.unpack_from('>f',event.payload,5)[0]
        if not math.isfinite(value) or not 0<=value<=1e9 or r.phase not in ('substage','active'):return []
        ack=Event(0x201,kind=0xb4,payload=bytes(4))
        if r.phase=='active':return [ack]
        r.loaded.add(s)
        for other in r.members:self.send(other,[Event(0x201,kind=0xb5,payload=struct.pack('>iQ',0,s.account.uid))])
        if len(r.loaded)==len(r.members):
            from els_server.domain.normal_fatigue_flow import shared_loaded
            try:deliveries=shared_loaded(r.members,event,lambda m:[e for e in LocalSession.handle(m,event)if e.kind not in(0xb4,0xb5)],room=r)
            except(ValueError,__import__('sqlite3').Error):
                r.loaded.discard(s);return[]
            for other,messages in deliveries:self.send(other,messages)
            r.loaded.clear();r.phase='active';r.deadline=0
            from els_server.domain.hunter_chest_flow import loaded as hunter_loaded
            hunter_loaded(s,event,dispatcher=self,room=r,broadcast_all=True)
            self.part_wait(r)
        return [ack]

    def death(self,r,s,event):
        from els_server.domain.native_script_loot import accepted_death as script_reward_death
        script_reply=script_reward_death(s,event,dispatcher=self,room=r)
        if script_reply is not None:return script_reply
        from els_server.domain.dungeon_lifecycle import death_report,death_ack
        from els_server.domain.hunter_chest_flow import accepted_death as hunter_death
        hunter_reply=hunter_death(s,event,dispatcher=self,room=r)
        if hunter_reply is not None:return hunter_reply
        from els_server.domain.friends_spawns import retire
        sentry_reply=retire(self,r,s,event)
        if sentry_reply is not None:return sentry_reply
        from els_server.domain.friends_story_retirements import retire as retire_story
        story_reply=retire_story(self,r,s,event)
        if story_reply is not None:return story_reply
        from els_server.domain.friends_material_loot import accepted_death as material_death
        material_reply=material_death(self,r,s,event)
        if material_reply is not None:return material_reply
        from els_server.domain.pve_economy_flow import group_death
        ordinary_reply=group_death(self,r,s,event)
        if ordinary_reply is not None:return ordinary_reply
        if r.phase!='active':
            from els_server.domain.friends_spawns import retry_death, retry_static_death
            return retry_death(self,r,s,event) or retry_static_death(self,r,s,event)
        if s is not r.leader:return []
        try:data=death_report(event.payload)
        except ValueError:return []
        # Summon ownership is a separate solo path and is not fanned out as an
        # enemy death or eligible clear in a shared room.
        if any(data['index'] in m.summon_keys for m in r.members):return []
        previous=r.leader.defeated_npcs.get(data['index'])
        reply=LocalSession.handle(s,event)
        if not any(e.kind==0xae for e in reply):return reply
        if previous is None:
            for other in r.members:
                if other is not s:
                    self.send(other,[e for e in LocalSession.handle(other,event) if e.kind!=0xae])
        self.part_wait(r)
        return reply

    def portal(self,r,s,event):
        if r.phase!='active':
            if r.phase!='substage':return []
            from els_server.domain.friends_spawns import retry_late_portal
            return retry_late_portal(self,r,s,event)
        # Each connection gets its own native wait acknowledgement. The room
        # master alone changes the shared source cursor.
        if s is not r.leader:
            run=s.dungeon_run
            valid=(run is not None and s.dungeon_substage_synced and not s.clear_notified
                   and event.payload==struct.pack('>b',run.part)
                   and all(n['key'] in run.defeated for n in run.current['npcs'] if n['active'] and n.get('team',1)!=0))
            return [Event(0x201,kind=0xb9,payload=i32(0 if valid else -1))]
        result=LocalSession.handle(s,event)
        if result and result[0].payload==bytes(4):
            for other in r.members:
                if other is not s:self.send(other,[e for e in LocalSession.handle(other,event) if e.kind!=0xb9])
        self.part_wait(r);return result

    def part_wait(self,r):
        if r.phase=='active' and all(s.part_end_notified for s in r.members):
            r.phase='part_end';r.deadline=time.monotonic()+45

    def end_part(self,r,s,event):
        part=s.dungeon_run.part if s.dungeon_run is not None else 0
        ack=Event(0x201,kind=0xbc,payload=bytes(4))
        if event.payload!=struct.pack('>b',part):
            previous=r.previous_part is not None and event.payload==struct.pack('>b',r.previous_part)
            return [ack] if previous else []
        if r.phase=='clear':return [ack]
        if r.phase!='part_end':return []
        static_transition=None
        if len(r.ended|{s})==len(r.members):
            from els_server.domain.friends_spawns import prepare_static_transition
            try:static_transition=prepare_static_transition(self,r,s)
            except (ValueError,OverflowError,struct.error,SessionOrderError):return []
        r.ended.add(s)
        if len(r.ended)!=len(r.members):return [ack]
        if r.party.get('challenge') and r.leader.dungeon_run.next['kind']==4:
            from els_server.storage.group_settlement import settle
            deliveries=settle(r.members,event)
            from els_server.domain.group_challenge import refresh
            refresh(r.party)
            for other,messages in deliveries:self.send(other,messages)
        elif ((r.leader.dungeon_run is None and r.identity==30000 and r.leader.gate_stage==2)or(r.leader.dungeon_run is not None and r.leader.dungeon_run.next['kind']==4))and __import__('els_server.domain.formal_pve_economy',fromlist=['definition']).definition(r.identity)is not None:
            from els_server.domain.pve_economy_flow import clear as clear_ordinary
            import sqlite3
            try:clear_ordinary(r.members,event,s,room=r)
            except(ValueError,sqlite3.Error,OverflowError,struct.error):
                r.ended.discard(s);return []
            except BaseException:
                r.ended.discard(s);raise
        elif raid_economy_managed(r.leader) and r.leader.dungeon_run.next['kind']!=0:
            from els_server.domain.raid_economy_flow import settle as settle_raid_phase
            import sqlite3
            try:settle_raid_phase(r.members,event,room=r)
            except (ValueError,sqlite3.Error,OverflowError,struct.error):
                r.ended.discard(s);return []
            except BaseException:
                r.ended.discard(s);raise
        else:
            from els_server.domain.normal_fatigue_flow import shared_loaded
            try:deliveries=shared_loaded(r.members,event,lambda m:[e for e in LocalSession.handle(m,event)if e.kind!=0xbc],room=r)
            except(ValueError,__import__('sqlite3').Error):
                r.ended.discard(s);return[]
            for other,messages in deliveries:self.send(other,messages)
        from els_server.domain.friends_spawns import advance
        advance(r)
        from els_server.domain.friends_spawns import commit_static_generation
        commit_static_generation(r,static_transition)
        r.ended.clear();r.previous_part=part
        if all(m.clear_notified for m in r.members):r.phase='clear';r.deadline=0
        elif any(not m.dungeon_substage_synced for m in r.members):
            r.phase='substage';r.deadline=time.monotonic()+60
        else:r.phase='active';r.deadline=0
        if r.phase=='active':
            from els_server.domain.hunter_chest_flow import loaded as hunter_loaded
            hunter_loaded(s,event,dispatcher=self,room=r,broadcast_all=True)
        self.part_wait(r)
        return [ack]

    def periodic(self,s):
        r=self.room(s)
        if r is None:return
        now=time.monotonic()
        if r.deadline and now>r.deadline:
            self.abort(r,'Party dungeon aborted: loading/transition timeout');return
        if r.phase=='active' and now-r.last_poll>=.25:
            from els_server.domain.dungeon_flow import periodic
            r.last_poll=now
            for other in r.members:self.send(other,periodic(other))
            self.part_wait(r)
