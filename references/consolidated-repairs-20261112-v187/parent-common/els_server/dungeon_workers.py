"""Bounded dungeon execution, serialized by party or solo account, not world jobs."""
import asyncio,threading,time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager,ExitStack
from contextvars import ContextVar
from weakref import WeakValueDictionary
from els_server.business_queue import BoundedBusinessQueue

KINDS=frozenset((0xd0,0xad,0xb8,0xbb,0xb3,0x471,0x9e))
_current=ContextVar('dungeon_execution_domain',default=None)

class _Domain:
    def __init__(self):self.lock=threading.RLock();self.members=()

class DungeonWorkers:
    def __init__(self,application):
        self.application=application
        self.workers=4
        self.executor=ThreadPoolExecutor(max_workers=self.workers,thread_name_prefix='els-dungeon')
        self.queue=BoundedBusinessQueue(self.executor,capacity=16)
        # Pickup waits for durable economic I/O. Retain its original domain
        # and retirement ownership without occupying death/door workers.
        self.death_workers=8
        self.death_executor=ThreadPoolExecutor(max_workers=self.death_workers,thread_name_prefix='els-death-waiter')
        self.death_queue=BoundedBusinessQueue(self.death_executor,capacity=self.death_workers)
        self.pickup_workers=8
        self.pickup_executor=ThreadPoolExecutor(max_workers=self.pickup_workers,thread_name_prefix='els-pickup')
        self.pickup_queue=BoundedBusinessQueue(self.pickup_executor,capacity=self.pickup_workers)
        # Location callers wait for durable batches. Their I/O waiting must
        # neither consume dungeon workers nor restrict batches to four rows.
        self.town_workers=8
        self.town_executor=ThreadPoolExecutor(max_workers=self.town_workers,thread_name_prefix='els-town')
        self.town_queue=BoundedBusinessQueue(self.town_executor,capacity=self.town_workers)
        self.town_preparation_admission=asyncio.Semaphore(2)
        self.town_selection_admission=asyncio.Semaphore(4)
        self.upkeep_workers=1
        self.upkeep_executor=ThreadPoolExecutor(max_workers=self.upkeep_workers,thread_name_prefix='els-upkeep')
        self.upkeep_queue=BoundedBusinessQueue(self.upkeep_executor,capacity=self.upkeep_workers)
        self.upkeep_admission=asyncio.Semaphore(self.upkeep_workers)
        self.town_upkeep_workers=1
        self.town_upkeep_executor=ThreadPoolExecutor(max_workers=self.town_upkeep_workers,thread_name_prefix='els-town-upkeep')
        self.town_upkeep_queue=BoundedBusinessQueue(self.town_upkeep_executor,capacity=self.town_upkeep_workers)
        self.town_upkeep_admission=asyncio.Semaphore(self.town_upkeep_workers)
        self.upkeep_available=None
        self.domains=WeakValueDictionary();self.admissions=WeakValueDictionary()
        self.catalog_lock=threading.RLock();self.metrics_lock=threading.Lock()
        self.active=0;self.peak=0;self.completed=0;self.threads=set();self.periodic_publish_skips=0;self.foreground_publish_skips=0

    def key(self,session):
        party=self.application.world.party_of.get(session)
        return ('party',id(party))if party is not None else('account',session.identity['id'])

    def death_waiter(self,function,args):
        # Routing only: the original handler/lease/SQL guards still authorize.
        if not args or getattr(args[0],'kind',None)!=0xad:return False
        session=getattr(function,'__self__',None);run=getattr(session,'dungeon_run',None)
        if run is None or getattr(run,'legacy_experience',None)is None:return False
        # Graph-backed solo AD uses the original fallback EXP consumer even
        # when its map also has formal clear/group rules (solo() returns None).
        return self.application.world.party_of.get(session)is None

    @staticmethod
    def town_preparation(function,args):
        from els_server.application import FriendsSession
        from els_server.protocol.protocol_codec import Event
        session=getattr(function,'__self__',None)
        if not(type(session)is FriendsSession and getattr(function,'__func__',None)is FriendsSession.handle
                and len(args)==1 and type(args[0])is Event and args[0].event_id==0x202
                and not session.released and session.client_build=='dx11_260923'
                and session.role=='game'
                and ((args[0].kind==0x227 and session.phase=='square_accepted')
                    or(args[0].kind==0x28 and session.phase in('characters_ready','channels_ready'))
                    or((args[0].kind,session.phase)in((0x6e9,'player_initialized'),(0x5bf,'skill_ui_ready'),(0x32,'initialization_confirmed'),(0x225,'map_loading')))
                    # Before selection these handlers read or update only this
                    # account. Existing handler guards still validate requests.
                    or(session.application.playing.get(session.identity['id'])is None
                        and(args[0].kind,session.phase)in((0x1e,'game_connected'),(0x35,'game_authenticated'),
                            (0x1ef,'port_ready'),(0x39,'session_ready'),(0x485,'terms_ready'),
                            (0x485,'session_ready'),(0x485,'channels_ready'),(0x490,'characters_ready'))))):return False
        world=session.application.world
        return(session not in world.members and world.party_of.get(session)is None
            and world.pvp.room(session)is None and world.racing.room(session)is None
            and world.field_bosses.room(session)is None and getattr(session,'active_challenge',None)is None)

    @staticmethod
    def solo_transition(function,args):
        from els_server.application import FriendsSession
        from els_server.protocol.protocol_codec import Event
        session=getattr(function,'__self__',None)
        if not(type(session)is FriendsSession and getattr(function,'__func__',None)is FriendsSession.handle
            and len(args)==1 and type(args[0])is Event and args[0].event_id==0x202
            and not session.released and session.client_build=='dx11_260923'and session.role=='game'
            and session.enter_dungeon and session.item_test
            and(args[0].kind,session.phase)in((0x7d4,'town_ready'),(0x382,'town_ready'),(0x91,'dungeon_loading'),(0x67,'dungeon_active'))):return False
        world=session.application.world
        if(world.party_of.get(session)is not None or world.dungeons.room(session)is not None
            or world.pvp.room(session)is not None or world.racing.room(session)is not None
            or world.field_bosses.room(session)is not None or getattr(session,'guild_agit',None)is not None
            or getattr(session,'photo_zone',None)is not None or getattr(session,'active_challenge',None)is not None
            or getattr(session,'requested_challenge',None)is not None or getattr(session,'solo_challenge_party',None)is not None):return False
        if args[0].kind==0x7d4:
            import struct
            if len(args[0].payload)!=8:return False
            mode,identity=struct.unpack('>ii',args[0].payload)
            if mode!=1:return False
        elif args[0].kind==0x382:
            if not session.dungeon_requested or session.requested_dungeon_mode!=1:return False
            identity=session.requested_dungeon_id
        else:identity=session.dungeon_id
        from els_server.domain.normal_fatigue_rules import route
        ordinary=route(identity)
        return ordinary is not None and ordinary['catalog']=='routes'

    @staticmethod
    def town_movement(function, args):
        from els_server.application import FriendsSession
        from els_server.protocol.protocol_codec import Event
        from els_server.domain.session_auxiliary import maintenance_request
        session = getattr(function, '__self__', None)
        if not (type(session) is FriendsSession and getattr(function, '__func__', None) is FriendsSession.handle and (len(args) == 1)):
            return False
        event = args[0]
        if maintenance_request(session, event) and event.kind == 555:
            return True
        return type(event) is Event and event.event_id == 514 and (event.kind == 1165) and session.application.world.party_of.get(session)is None and DungeonWorkers.town_periodic(session.periodic_notifications, ()) and (session.application.world.members.get(session) == (1, session.active_map))

    @staticmethod
    def town_metadata(function,args):
        return(bool(args)and getattr(args[0],'kind',None)==0x48d
            and DungeonWorkers.town_movement(function,args))

    @staticmethod
    def town_peer_delivery(function,args):
        return(DungeonWorkers.ordinary_town_move(function,args)
            or DungeonWorkers.town_metadata(function,args))

    @staticmethod
    def ordinary_town_move(function,args):
        if not DungeonWorkers.town_movement(function,args)or args[0].kind!=0x22b:return False
        session=function.__self__;world=session.application.world
        return(world.party_of.get(session)is None and DungeonWorkers.town_periodic(session.periodic_notifications,())
            and world.members.get(session)==(1,session.active_map)
            and world.dungeons.room(session)is None
            and session not in world.racing.queue and session not in world.racing.offers
            and getattr(session,'guild_agit',None)is None
            and getattr(session,'photo_zone',None)is None
            and session not in world.player_trades.by_session)

    @staticmethod
    def town_periodic(function,args):
        from els_server.application import FriendsSession
        session=getattr(function,'__self__',None)
        if not(type(session)is FriendsSession and not args
                and getattr(function,'__func__',None)is FriendsSession.periodic_notifications
                and not session.released and session.role=='game'
                and session.client_build=='dx11_260923'and session.phase=='town_ready'):return False
        world=session.application.world
        party=world.party_of.get(session)
        # Waiting parties have the same own-town upkeep as ungrouped actors.
        # Sending every waiting member through world writers can starve the
        # next invitee's background reader before its mailbox is ever polled.
        return((party is None or party.get('run')is None)and world.dungeons.room(session)is None and world.pvp.room(session)is None
            and world.racing.room(session)is None and world.field_bosses.room(session)is None
            and getattr(session,'active_challenge',None)is None)

    @staticmethod
    def town_mailbox(function,args):
        session=getattr(function,'__self__',None)
        return(DungeonWorkers.town_periodic(function,args)
            and not getattr(session,'_periodic_pending',False)
            and time.monotonic()<session.next_periodic
            and bool(session.mailbox.moves)and not session.mailbox.messages)

    @staticmethod
    def candidate(function,args):
        from els_server.application import FriendsSession
        from els_server.protocol.protocol_codec import Event
        from els_server.domain.dungeon_requests import accepts
        s=getattr(function,'__self__',None)
        if(type(s)is FriendsSession and getattr(function,'__func__',None)is FriendsSession.periodic_notifications and not args):
            return accepts(s,Event(0x202,kind=0xb3))or DungeonWorkers.town_periodic(function,args)
        return DungeonWorkers.town_preparation(function,args)or DungeonWorkers.solo_transition(function,args)or DungeonWorkers.town_movement(function,args)or(type(s)is FriendsSession and getattr(function,'__func__',None)is FriendsSession.handle
                and len(args)==1 and type(args[0])is Event and args[0].kind in KINDS and accepts(s,args[0]))

    def isolated(self,session,event):
        current=_current.get()
        return current is not None and current[0]is session and event.kind in KINDS and self.candidate(session.handle,(event,))

    def session_for(self,function,args):
        from els_server.application import FriendsSession
        s=getattr(function,'__self__',None)
        if type(s)is FriendsSession:return s
        explicit=getattr(function,'_dungeon_session',None)
        if type(explicit)is FriendsSession:return explicit
        if s is self.application.world and args and type(args[0])is FriendsSession:return args[0]
        if s is self.application.world.dungeons and function.__name__ in('manifest','relay_target','relay_lost')and len(args)>=2:
            return self.application.playing.get(args[1])
        if getattr(function,'__module__',None)=='els_server.friends_relay'and getattr(function,'__name__',None)=='relay_lost_current'and len(args)>=2:
            return self.application.playing.get(args[1])
        return None

    @contextmanager
    def scope(self,session,*,mailboxes=True):
        # Party identity is stable through admission, load, clear and detach.
        # Recheck after waiting because the preceding member may have left.
        while True:
            key,domain=self._domain_for(session)
            domain.lock.acquire()
            if self.key(session)==key:break
            domain.lock.release()
        try:
            party=self.application.world.party_of.get(session)
            members=tuple(party['members'])if party is not None else(session,)
            with self.catalog_lock:domain.members=members
            # Prepared mailbox replacements copy this same RLock. Retain it
            # through pre-encoding, SQL commit and adoption, so a concurrent
            # announcement cannot disappear between snapshot and replacement.
            with ExitStack()as boxes:
                if mailboxes:
                    for member in sorted(members,key=lambda s:s.identity['id']):boxes.enter_context(member.mailbox.lock)
                token=_current.set((session,domain))
                try:yield
                finally:_current.reset(token)
        finally:domain.lock.release()

    def _domain_for(self,session):
        key=self.key(session)
        with self.catalog_lock:
            domain=self.domains.get(key)
            if domain is None:
                domain=_Domain()
                party=self.application.world.party_of.get(session)
                domain.members=tuple(party['members'])if party is not None else(session,)
                self.domains[key]=domain
        return key,domain

    @contextmanager
    def mailbox_scope(self,session,*,recipients=()):
        party=self.application.world.party_of.get(session)
        members=tuple(party['members'])if party is not None else(session,)
        with ExitStack()as boxes:
            for member in sorted(set(members)|set(recipients),key=lambda s:s.identity['id']):boxes.enter_context(member.mailbox.lock)
            yield

    @contextmanager
    def worker_scope(self,function,args):
        session=self.session_for(function,args)
        manager=getattr(self.application,'activity2026_manager',None)
        source=getattr(function,'__self__',None)
        gm_actor_access=(getattr(function,'__module__',None)=='els_server.gm_runtime'
            and getattr(source,'app',None)is self.application
            and(function.__name__ in('give','players')or(function.__name__=='execute'and args and args[0].get('action')in('give','selected2026','status'))))
        if gm_actor_access or(manager is not None and source is manager and function.__name__=='update'):
            # GM reads and updates retain actor ownership before world/SQL.
            # Identity, balances and phase must not span an actor's adoption.
            # A grant replay may have no online recipient; world decides that.
            while True:
                with ExitStack()as scopes:
                    members=sorted(self.application.playing.copy().values(),key=lambda s:s.identity['id'])
                    for member in members:scopes.enter_context(self.scope(member,mailboxes=False))
                    scopes.enter_context(self.application.world_lock)
                    # Native selection may add a playing lease while this
                    # operation waits for actor locks. Include that actor before
                    # reading or updating those actors under the world lock.
                    playing=self.application.playing
                    if len(playing)!=len(members)or any(playing.get(s.identity['id'])is not s for s in members):continue
                    for member in members:scopes.enter_context(member.mailbox.lock)
                    yield
                return
        elif session is None:yield
        else:
            with self.scope(session,mailboxes=False):
                if self.ordinary_town_move(function,args):
                    # This notification cannot publish guild or trade changes.
                    # Its normal handler retains the one world section which
                    # broadcasts and drains mail after saving own coordinates.
                    yield
                elif self.town_preparation(function,args)or self.solo_transition(function,args)or self.town_movement(function,args)or self.town_periodic(function,args)or self.application.economy.candidate(function,args):
                    # These own-actor receipt/location operations prepare no
                    # mailbox replacement. Original world sections serialize
                    # membership, peer effects and draining after their SQL.
                    from els_server.domain.guild_publication import targets
                    with ExitStack()as shared:
                        shared.enter_context(self.application.world_lock)
                        recipients=set(targets(session,function,args))
                        recipients.update(self.application.world.player_trades.targets(session,function,args))
                        if recipients:shared.enter_context(self.mailbox_scope(session,recipients=recipients))
                        else:shared.close()
                        yield
                elif self.candidate(function,args):
                    with self.mailbox_scope(session):yield
                else:
                    # Town senders hold world before taking a recipient box.
                    # World operations must use that same order; acquiring a
                    # mailbox while waiting for world can deadlock broadcasts.
                    from els_server.domain.guild_publication import targets
                    with self.application.world_lock:
                        recipients=set(targets(session,function,args))
                        recipients.update(self.application.world.player_trades.targets(session,function,args))
                        with self.mailbox_scope(session,recipients=recipients):yield

    async def run(self,session,work,*,timing,town=False,pickup=False,death=False,preparation=False,selection=False):
        key=self.key(session)
        gate=self.admissions.get(key)
        if gate is None:gate=asyncio.Lock();self.admissions[key]=gate
        async with gate:
            def invoke():
                with self.metrics_lock:
                    self.active+=1;self.peak=max(self.peak,self.active);self.threads.add(threading.get_ident())
                try:return work()
                finally:
                    with self.metrics_lock:self.active-=1;self.completed+=1
            # Existing queue waits for actual SQL retirement on cancellation.
            queue=self.town_queue if town else self.pickup_queue if pickup else self.death_queue if death else self.queue
            if preparation:
                # Bound heavy own-role preparation without occupying the
                # dungeon/door or fourteen other town movement workers.
                # Fifty selections must not sit ahead of actors whose
                # selection completed and whose native227 is already ready.
                admission=self.town_selection_admission if selection else self.town_preparation_admission
                async with admission:return await queue.run(invoke,timing=timing)
            return await queue.run(invoke,timing=timing)

    def upkeep_admission_for(self,session):
        return self.town_upkeep_admission if self.town_periodic(session.periodic_notifications,())else self.upkeep_admission

    def release_upkeep(self,semaphore):
        semaphore.release()
        if self.upkeep_available is not None:self.upkeep_available()

    async def run_upkeep(self,session,work,*,timing,claim=None,world_background=True):
        # The socket operation/claim and actual worker domain serialize this
        # work. A queued, cancelled claim must not retain foreground admission.
        # Reserve real upkeep capacity before excluding world mutations.
        # Waiting actors must not occupy sixteen world-reader admissions
        # while only two upkeep workers can actually make progress.
        reserved=claim.upkeep_reserved if claim is not None else None
        semaphore=reserved or self.upkeep_admission_for(session)
        queue=self.upkeep_queue if semaphore is self.upkeep_admission else self.town_upkeep_queue
        async def admitted():
            if claim is not None and claim.cancelled:return None
            if not world_background:
                if claim is not None and not claim.admit():return None
                return await queue.run(work,timing=timing)
            async with self.application.world_gate.background():
                if claim is not None and not claim.admit():return None
                return await queue.run(work,timing=timing)
        if reserved:
            claim.upkeep_reserved=False
            try:return await admitted()
            finally:self.release_upkeep(semaphore)
        if claim is not None and claim.cancelled:return None
        await semaphore.acquire()
        try:return await admitted()
        finally:self.release_upkeep(semaphore)

    def publish(self,function,args,*,failed=False,periodic=False,independent=False):
        app=self.application;acquired=[];busy=set()
        # Never wait for the world lock while holding the domain catalog:
        # teardown can already own world and re-enter its existing domain.
        if not app.world_lock.acquire(blocking=not independent):return
        # Publish completed domains without reading another room mid-adoption.
        # New domains cannot enter while the snapshot's lock list is captured.
        try:
            from els_server.domain.session_auxiliary import maintenance_request
            source=getattr(function,'__self__',None)
            movement=(getattr(function,'__name__','')=='handle'and len(args)==1
                and maintenance_request(source,args[0])and args[0].kind==0x22b)
            # The existing exact domain fingerprint decides reuse; changed
            # stage, scene, party or routing facts still force publication.
            unchanged_foreground=movement or(independent and args and self.candidate(function,args)and args[0].kind in(0xd0,0xad,0xb8,0x9e))
            if (periodic or unchanged_foreground)and not failed:
                session=self.session_for(function,args)
                if session is not None:
                    _,domain=self._domain_for(session)
                    if domain.lock.acquire(blocking=False):
                        try:
                            party=app.world.party_of.get(session)
                            domain.members=tuple(party['members'])if party is not None else(session,)
                            if app.realtime.unchanged_scope(app,domain.members):
                                if periodic:self.periodic_publish_skips+=1
                                else:self.foreground_publish_skips+=1
                                return
                        finally:domain.lock.release()
            with self.catalog_lock:
                for domain in list(self.domains.values()):
                    if domain.lock.acquire(blocking=False):acquired.append(domain.lock)
                    else:busy.update(s.identity['id']for s in domain.members)
                try:
                    # Reuse prewarmed per-worker read-only handles, while this
                    # publication still SELECTs fresh authorization. No role
                    # or enabled-account values survive the operation scope.
                    from els_server.storage.read_scope import committed_reads
                    with committed_reads(connections=app.read_connections):
                        app.realtime.publish(app,function,args,failed=failed,periodic=periodic,exclude=frozenset(busy))
                finally:
                    for lock in reversed(acquired):lock.release()
        finally:app.world_lock.release()

    def snapshot(self):
        with self.metrics_lock:return dict(active=self.active,peak=self.peak,completed=self.completed,threads=len(self.threads),workers=self.workers,death_workers=self.death_workers,death_queue=self.death_queue.snapshot(),pickup_workers=self.pickup_workers,pickup_queue=self.pickup_queue.snapshot(),periodic_publish_skips=self.periodic_publish_skips,foreground_publish_skips=self.foreground_publish_skips,queue=self.queue.snapshot(),town_workers=self.town_workers,town_queue=self.town_queue.snapshot(),town_upkeep_workers=self.town_upkeep_workers,town_upkeep_queue=self.town_upkeep_queue.snapshot(),upkeep_workers=self.upkeep_workers,upkeep_queue=self.upkeep_queue.snapshot())

    def close(self):
        self.town_upkeep_queue.close();self.death_queue.close();self.queue.close();self.pickup_queue.close();self.town_queue.close();self.upkeep_queue.close()
        self.town_upkeep_executor.shutdown(wait=True,cancel_futures=True);self.death_executor.shutdown(wait=True,cancel_futures=True);self.executor.shutdown(wait=True,cancel_futures=True);self.pickup_executor.shutdown(wait=True,cancel_futures=True);self.town_executor.shutdown(wait=True,cancel_futures=True);self.upkeep_executor.shutdown(wait=True,cancel_futures=True)
