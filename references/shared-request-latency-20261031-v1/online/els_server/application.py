"""Serialized business operations with local or authenticated account sessions."""
import asyncio
import time
from els_server.performance import OperationMetrics
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from els_server.domain.local_session import LocalAccount,LocalSession,SessionOrderError
from els_server.storage.local_state import LocalState


class FriendsSession(LocalSession):
    """One playable connection per account; frontend/channel handoffs may coexist."""
    def __init__(self,application,identity,account,**options):
        self.application=application;self.identity=identity;self.released=False
        from els_server.domain.friends_world import Mailbox
        self.mailbox=Mailbox();self.chat_times=deque();self.invite_times=deque();self.social_overflow=False
        self.next_periodic=0
        self.coop_error=None
        super().__init__(account,**options)

    def activity_reply(self,replies):
        return self.activity2026_awards.finalize(self,replies) if self.activity2026_awards is not None else replies

    def handle(self,event,request_sequence=None):
        if self.released or not self.application.registry.enabled(self.identity['id']):raise SessionOrderError('Account is offline or disabled')
        if self.social_overflow:raise SessionOrderError('Social consumer is too slow')
        if self.coop_error:raise SessionOrderError(self.coop_error)
        # The fixed DX11 capture's 7D0 is an unconsumed nine-byte auxiliary
        # notification, emitted five times a second. It has no domain handler.
        # Authentication and stream sequencing still run. The existing
        # independent periodic path performs online-clock persistence and
        # expiry/quest/activity work; never rebuild all wire projections here.
        from els_server.domain.session_auxiliary import friends_auxiliary_noop
        if friends_auxiliary_noop(self,event):
            return self.mailbox.drain()
        result=self.application.world.field_bosses.request(self,event)
        if result is not None:return self.activity_reply(result+self.mailbox.drain())
        # Persist the native final selector before ordinary dungeon detach.
        from els_server.domain.luciel_native_end import handle as luciel_end_handle
        result=luciel_end_handle(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self.mailbox.drain())
        result=self.application.world.dungeons.request(self,event,request_sequence)
        if result is not None:
            if self.phase!='town_ready' or self.active_map!=20013:
                from els_server.domain.tenebros_storage_flow import abandon as abandon_shadow
                abandon_shadow(self)
            return self.activity_reply(result+self.mailbox.drain())
        if event.event_id==0x202 and event.kind==0x85:
            return self.application.world.chat(self,event)+self.mailbox.drain()
        if event.event_id==0x202:
            result=self.application.world.party_request(self,event)
            if result is not None:return result+self.mailbox.drain()
        selecting=event.event_id==0x202 and event.kind==0x28
        leases=self.application.playing
        acquired=False
        if selecting:
            old=leases.get(self.identity['id'])
            if old is not None and old is not self:raise SessionOrderError('Account already playing')
            if old is None:leases[self.identity['id']]=self;acquired=True
        try:
            result=super().handle(event,request_sequence)
        except BaseException:
            if acquired:leases.pop(self.identity['id'],None)
            raise
        if self.phase in ('closing','channels_ready') and leases.get(self.identity['id']) is self:
            self.application.world.leave_party(self)
            leases.pop(self.identity['id'],None)
        if event.event_id==0x202 and event.kind==0x113:
            from els_server.domain.apple_consumables import relay_committed_use
            relay_committed_use(self,result)
        if event.event_id==0x202 and event.kind in (0x2e8,0x2ec,0x432,0x42c,0x42f,0x2f5,0x2fb,0x8c7,0x219):
            from els_server.domain.companion_peer_sync import invalidate as invalidate_companion_peer
            invalidate_companion_peer(self)
        if event.event_id==0x202 and event.kind==0x219:
            from els_server.domain.elixir_peer_sync import relay as relay_world_elixirs
            relay_world_elixirs(self)
        self.application.world.synchronize(self)
        if event.event_id==0x202 and event.kind==0x4cb:
            self.application.world.custom_changed(self,result)
        if self.phase=='town_ready' and event.event_id==0x202 and event.kind==0x22b:
            self.application.world.moved(self,event.payload)
        if self.phase=='town_ready' and event.event_id==0x202:
            kinds={e.kind for e in result if e.event_id==0x201}
            luciel=self.account.character_identity()['unit_type']==10
            career=luciel and event.kind in (0x219,0x80f) and bool(kinds&{0x29f,0x59f})
            expiry=0x1c6 in kinds
            mystic=event.kind==0x6e7 and any(e.event_id==0x201 and e.kind==0x6e8 and len(e.payload)>=40 and e.payload[:4]==bytes(4) and e.payload[-16:-12]==bytes((0,0,0,4)) for e in result)
            if event.kind in (0x104,0x213) or career or expiry or mystic or (event.kind==0x8b1 and any(e.kind==0x8b2 and e.payload[:4]==bytes(4) for e in result)) or (event.kind in (0x4b1,0x6d7,0xad6) and any(e.kind==event.kind+1 and e.payload[:4]==bytes(4) for e in result)):
                # Reuse the existing current-instance/learned-skill projection
                # for peers only; never restore or heal the owner again.
                self.application.world.appearance_changed(self)
        return result+self.mailbox.drain()

    def _relay_luciel_hp_expiry(self,messages):
        # Retain the exact committed notice until every native member is ready.
        # Room identity and source UID prevent a later admission from reusing it.
        pending=getattr(self,'luciel_peer_hp_expiry_pending',None)
        notices=tuple(e for e in messages if e.event_id==0x201 and e.kind==0x70d) if any(e.event_id==0x201 and e.kind==0x1c6 for e in messages) else ()
        if not notices and pending is None:return
        source=self.luciel_dungeon_hp_source
        dispatcher=self.application.world.dungeons;room=dispatcher.room(self)
        if self.released or source is None or source[0]!=self.account.uid or room is None:
            self.luciel_peer_hp_expiry_pending=None;return
        if notices:
            pending=(room,self.account.uid,notices)
            self.luciel_peer_hp_expiry_pending=pending
        if pending[0] is not room or pending[1]!=self.account.uid:
            self.luciel_peer_hp_expiry_pending=None;return
        if room.phase!='active' or self.phase!='dungeon_active' or not self.dungeon_substage_synced:return
        peers=[p for p in room.members if p is not self and not p.released and dispatcher.room(p) is room]
        if any(p.phase!='dungeon_active' or not p.dungeon_substage_synced for p in peers):return
        for peer in peers:dispatcher.send(peer,list(pending[2]))
        self.luciel_peer_hp_expiry_pending=None

    def expiration_notifications(self):
        # Both request handling and the existing periodic path use this exit.
        # Super returns only after atomic removal/encoding/cache commit.
        messages=super().expiration_notifications()
        self._relay_luciel_hp_expiry(messages)
        from els_server.domain.elixir_peer_sync import relay as relay_world_elixirs
        relay_world_elixirs(self)
        return messages

    def periodic_notifications(self, *, _rooms=None):
        from els_server.domain.group_challenge import tick
        tick(self)
        self.application.world.field_bosses.periodic(self)
        if not self.application.registry.enabled(self.identity['id']):raise SessionOrderError('Account disabled')
        if self.social_overflow:raise SessionOrderError('Social consumer is too slow')
        room=self.application.world.dungeons.room(self)
        if _rooms is None or room is None or room not in _rooms:
            self.application.world.dungeons.periodic(self)
            if _rooms is not None and room is not None:_rooms.add(room)
        if self.coop_error:raise SessionOrderError(self.coop_error)
        now=time.monotonic();messages=[]
        if now>=self.next_periodic:
            self.next_periodic=now+1
            if self.application.world.dungeons.room(self) is None:messages=super().periodic_notifications()
            else:
                from els_server.domain.mount_flow import periodic as mount_periodic
                from els_server.domain.title_flow import periodic as title_periodic
                messages=self.expiration_notifications()+self._periodic_notifications()+mount_periodic(self)+title_periodic(self)
                messages=self.activity_reply(messages)
            from els_server.domain.resonance_flow import synchronize as shared_resonance_sync
            messages=shared_resonance_sync(self,messages)
            if self.phase=='town_ready':
                kinds={e.kind for e in messages if e.event_id==0x201}
                expiry=0x1c6 in kinds
                if 0x214 in kinds or expiry:self.application.world.appearance_changed(self)
            from els_server.domain.companion_peer_sync import receive as companion_peer_receive
            messages+=companion_peer_receive(self,now=now)
        return self.mailbox.drain()+messages


    def release(self):
        try:
            self.application.world.disconnect(self)
        finally:
            if self.application.playing.get(self.identity['id']) is self:self.application.playing.pop(self.identity['id'])
            self.released=True


class Application:
    def __init__(self, config, *, activity2026_awards_factory=None):
        self.config=config
        self.activity2026_awards_factory=activity2026_awards_factory
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='els-account')
        from els_server.business_queue import BoundedBusinessQueue
        self.business_queue=BoundedBusinessQueue(self.executor)
        self.performance=OperationMetrics()
        from els_server.preparation import BoundedPreparation
        self.preparation=BoundedPreparation()
        self._aux_local_sessions=set()
        self._executor_closed=False
        self.account=None
        from els_server.account_cache import AccountCache
        self.registry=None;self.accounts=AccountCache();self.playing={}
        from els_server.domain.friends_world import FriendsWorld
        self.world=FriendsWorld()

    async def call(self, function, *args, **kwargs):
        from els_server.performance import captured_calls
        submitted=time.perf_counter();queue_timing={}
        return await self.business_queue.run(
            partial(self._worker_call,function,args,kwargs,submitted,captured_calls(),queue_timing),
            timing=queue_timing)

    def _worker_call(self,function,args,kwargs,submitted,capture=None,queue_timing=None):
        from els_server.performance import captured_calls,worker_timing,request_category
        sample=dict(clock_before_ms=0.,domain_ms=0.,clock_after_ms=0.,after_reply_ms=0.,queue_ms=0.,admission_ms=0.,executor_ms=0.,batch_wait_ms=0.,handler_ms=0.,projection_ms=0.,projection_loads=0,projection_hits=0,registry_ms=0.,registry_checks=0,sql_begin_wait_ms=0.,sql_finish_wait_ms=0.,sql_finish_busy=0,sql_writer_held_ms=0.,sql_busy=0,sql_rollbacks=0,failed=True)
        def invoke():
            started=time.perf_counter();sample['queue_ms']=(started-submitted)*1000
            request=request_category(function,args)
            if queue_timing is not None:
                admitted=queue_timing.get('admitted_at',submitted)
                batch_started=queue_timing.get('batch_started_at',started)
                sample['admission_ms']=(admitted-submitted)*1000
                sample['executor_ms']=(batch_started-admitted)*1000
                sample['batch_wait_ms']=(started-batch_started)*1000
            try:
                with worker_timing(sample):
                    from els_server.domain.native_session_sources import capture as capture_native_sources
                    result=capture_native_sources(function,args,kwargs,invoke_scoped)
                sample['failed']=False
                return result
            finally:
                sample['handler_ms']=(time.perf_counter()-started)*1000
                self.performance.record(getattr(function,'__name__','other'),sample,request=request)
                if capture is not None:capture.append(dict(sample))
        def invoke_scoped():
            from els_server.storage.read_scope import committed_reads
            with committed_reads():
                return invoke_with_reads()
        def invoke_with_reads():
            from els_server.domain.session_auxiliary import auxiliary_call,activity_due
            if auxiliary_call(function,args):
                started=time.perf_counter()
                try:return function(*args,**kwargs)
                finally:sample['domain_ms']=(time.perf_counter()-started)*1000
            session=getattr(function,'__self__',None)
            timer=getattr(getattr(session,'activity2026_awards',None),'online',None)
            activity=isinstance(session,LocalSession) and function.__name__ in ('handle','periodic_notifications') and timer is not None
            observed=activity and activity_due(function)
            if observed:
                started=time.perf_counter()
                try:timer.observe(session)
                finally:sample['clock_before_ms']=(time.perf_counter()-started)*1000
            started=time.perf_counter()
            try:
                result=function(*args,**kwargs)
            finally:
                sample['domain_ms']=(time.perf_counter()-started)*1000
                if observed:
                    started=time.perf_counter()
                    try:timer.observe(session)
                    finally:sample['clock_after_ms']=(time.perf_counter()-started)*1000
            flow=getattr(session,'activity2026_awards',None) if activity and (observed or result) else None
            after=getattr(flow,'after_reply',None)
            if after is None:return result
            started=time.perf_counter()
            try:return after(session,result)
            finally:sample['after_reply_ms']=(time.perf_counter()-started)*1000
        return invoke()


    async def periodic_batch(self,sessions):
        # At most one scheduler batch is queued. Each member retains an
        # independent committed-read scope and before/after activity clock.
        if len(sessions)>16:raise ValueError('Periodic batch bounds')
        submitted=time.perf_counter();queue_timing={}
        def invoke():
            queue_timing['batch_started_at']=time.perf_counter()
            rooms=set();result=[]
            for session in sessions:
                options={'_rooms':rooms} if isinstance(session,FriendsSession) else {}
                try:
                    messages=self._worker_call(session.periodic_notifications,(),options,submitted,queue_timing=queue_timing)
                    result.append((messages,None))
                except Exception as error:result.append((None,error))
            return result
        return await self.business_queue.run(invoke,timing=queue_timing)

    def periodic_chunks(self,sessions):
        from els_server.periodic_work import periodic_chunks
        return periodic_chunks(self,sessions)

    async def start(self):
        def initialize():
            from els_server.domain.owned_growth_items import install as install_owned_growth
            install_owned_growth()
            from els_server.game_data import client_data
            client_data().npcs  # Verify both pinned definition packs before opening a save.
            from els_server.domain.reward_rules import dungeon_rewards
            dungeon_rewards(30000)
            if self.config.profile=='integrated_dx11':
                from els_server.domain.dungeon_routes import route_catalog
                from els_server.domain.dungeon_flow import local_rewards
                from els_server.domain.region_quests import region_catalog
                from els_server.domain.dungeon_rotation import rotation
                route_catalog();local_rewards();region_catalog();rotation()
            if self.config.profile=='integrated_dx11':
                from els_server.storage.characters import prepare_character_catalogs
                prepare_character_catalogs()  # Before opening a player writer or listener.
            account=LocalAccount(LocalState(self.config.state_file) if self.config.profile=='integrated_dx11' else None)
            # Validate feature dependencies and initialize tables before listening.
            LocalSession(account,**self.config.session_options())
            if self.config.profile=='integrated_dx11':
                from els_server.storage.game_mail import initialize as initialize_mail
                initialize_mail(self.config.state_file)
            if self.config.profile=='integrated_dx11':account.enable_characters()
            return account
        self.account=await self.call(initialize)
        if self.config.mode=='friends':
            from els_server.storage.accounts import Accounts
            self.registry=await self.call(Accounts,self.config.accounts_file)
        from els_server.domain.selected_2026_friends import install as install_friends_activities
        await self.call(install_friends_activities,self)
        from els_server.domain.black_market_flow import run_application as market_runtime
        self._black_market_alive=True
        self._black_market_task=asyncio.create_task(market_runtime(self))

    def activity_options(self,account):
        return {'activity2026_awards':self.activity2026_awards_factory(account)} if self.activity2026_awards_factory is not None else {}

    async def session(self,port_probe_port=1,identity=None):
        if self.config.mode=='local':
            def create_local():
                session=LocalSession(self.account,port_probe_port=port_probe_port,**self.config.session_options(),**self.activity_options(self.account))
                # Dedicated reset witness; preserve generic local .application absence.
                session._chip_reset_local_application=self
                session._chip_reset_local_live=True
                session._c1_local_application=self
                session._c1_local_live=True
                session._aux_local_application=self
                session._aux_local_live=True
                self._aux_local_sessions.add(session)
                return session
            return await self.call(create_local)
        if identity is None:raise SessionOrderError('Authentication required')
        def create():
            key=identity['id']
            account=self.accounts.get(key)  # Hold one strong root across construction/handoff.
            if account is None:
                from els_server.storage.characters import Characters
                roster=Characters(self.config.state_file,key)
                roles=roster.list()
                if roles:
                    account=LocalAccount(LocalState(self.config.state_file,roles[0]['uid']),key,identity['name'])
                    account.enable_characters(characters=roster)
                else:
                    from els_server.domain.roster_account import RosterAccount
                    account=RosterAccount(self.config.state_file,key,identity['name'],characters=roster)
                    account.enable_characters()
                self.accounts[key]=account
            return FriendsSession(self,identity,account,port_probe_port=port_probe_port,**self.config.session_options(),**self.activity_options(self.accounts[key]))
        return await self.call(create)

    async def release(self,session):
        from els_server.domain.mount_flow import close as close_mount
        def release():
            from els_server.cleanup import cleanup_all
            from els_server.domain.guild_agit_flow import disconnect as guild_disconnect
            from els_server.domain.tenebros_storage_flow import abandon as abandon_shadow
            timer=getattr(getattr(session,'activity2026_awards',None),'online',None)
            def auxiliary():
                self._aux_local_sessions.discard(session)
                session._aux_local_live=False
            def local_flags():
                if type(session) is LocalSession and getattr(session,'_c1_local_application',None) is self:
                    session._c1_local_live=False
                    if getattr(self,'_c1_local_context',None) is getattr(session,'_c1_hp_context',None):
                        self._c1_local_context=None
                if type(session) is LocalSession and getattr(session,'_chip_reset_local_application',None) is self:
                    session._chip_reset_local_live=False
            cleanup_all(lambda:guild_disconnect(session), auxiliary,
                lambda:abandon_shadow(session), lambda:close_mount(session), local_flags,
                lambda:timer.observe(session,stop=True) if timer is not None else None,
                lambda:session.release() if isinstance(session,FriendsSession) else None)
        # One worker operation owns all teardown stages. A failed persistence
        # or timer operation must not strand the account's playing lease.
        cleanup=asyncio.create_task(self.call(release))
        try:
            # Cancellation of a socket task must not cancel cleanup that is
            # still waiting behind an earlier operation in the worker queue.
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            def report_failure(task):
                if not task.cancelled():
                    error=task.exception()
                    if error is not None:
                        task.get_loop().call_exception_handler(dict(
                            message='Session cleanup failed after cancellation',exception=error))
            cleanup.add_done_callback(report_failure)
            raise

    def close(self):
        # Running SQL is allowed to commit/rollback before releasing save ownership.
        self._black_market_alive=False
        task=getattr(self,'_black_market_task',None)
        if task is not None:task.cancel()
        if not self._executor_closed:
            self._executor_closed=True
            self.business_queue.close()
            try:
                close=getattr(self.registry,'close',None)
                if close is not None:self.executor.submit(close).result()
            finally:
                self.executor.shutdown(wait=True,cancel_futures=True)
                self.preparation.close()
