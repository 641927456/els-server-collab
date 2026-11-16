"""Coordinated world operations and account-local economic workers."""
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

    def _mailbox_messages(self):
        messages=self.mailbox.drain()
        # A peer's committed guild departure can replace this actor's quest
        # list. Merge this recipient's account task through the same projector
        # used by ordinary own replies, after the sender's writer has ended.
        if self.activity2026_awards is not None and any(e.event_id==0x201 and e.kind==0x2b for e in messages):
            messages=self.activity2026_awards.finalize(self,messages)
        return messages

    def activity_reply(self,replies):
        replies=self.activity2026_awards.finalize(self,replies) if self.activity2026_awards is not None else replies
        from els_server.domain.growth_guide_flow import synchronize as guide_sync
        from els_server.domain.elixir_flow import remember
        from els_server.domain.elixir_peer_sync import relay
        replies=remember(self,guide_sync(self,replies))
        relay(self)
        from els_server.domain.modern_ice_flow import synchronize as ice_sale_sync
        return ice_sale_sync(self,replies)

    def _shared_request(self,event,request_sequence):
        # The fixed DX11 capture's 7D0 is an unconsumed nine-byte auxiliary
        # notification, emitted five times a second. It has no domain handler.
        # Authentication and stream sequencing still run. The existing
        # independent periodic path performs online-clock persistence and
        # expiry/quest/activity work; never rebuild all wire projections here.
        from els_server.domain.elixir_flow import remember
        from els_server.domain.session_auxiliary import friends_auxiliary_noop
        if friends_auxiliary_noop(self,event):
            return remember(self,self._mailbox_messages())
        from els_server.domain.photo_zone_flow import handle as photo_handle
        result=photo_handle(self,event,request_sequence)
        if result is not None:
            self.application.world.synchronize(self)
            if event.kind==0x5b4 and getattr(self,'photo_zone',None) is not None:
                from els_server.domain.friend_flow import synchronize
                room=self.photo_zone['room']
                if room is not None:
                    for peer in room['members']:
                        if peer is not self:synchronize(peer,event,[])
            return self.activity_reply(result+self._mailbox_messages())
        from els_server.domain.friend_flow import handle as friend_handle
        result=friend_handle(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.player_trades.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.racing.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.pvp.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.field_bosses.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        # Persist the native final selector before ordinary dungeon detach.
        from els_server.domain.luciel_native_end import handle as luciel_end_handle
        result=luciel_end_handle(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self._dungeon_request(event,request_sequence)
        if result is not None:return result
        if event.event_id==0x202 and event.kind==0x85:
            return remember(self,self.application.world.chat(self,event)+self._mailbox_messages())
        if event.event_id==0x202:
            result=self.application.world.party_request(self,event)
            if result is not None:return remember(self,result+self._mailbox_messages())
        return None

    def _dungeon_request(self,event,request_sequence):
        from els_server.domain.elixir_flow import remember
        from els_server.domain.dungeon_requests import accepts,identity_before,activity_changed
        dungeon_before=identity_before(self,event)
        result=self.application.world.dungeons.request(self,event,request_sequence)
        if result is not None:
            if self.phase!='town_ready' or self.active_map!=20013:
                from els_server.domain.tenebros_storage_flow import abandon as abandon_shadow
                abandon_shadow(self)
            if accepts(self,event) and not activity_changed(self,event,result,dungeon_before):
                from els_server.domain.growth_guide_flow import synchronize as guide
                return remember(self,guide(self,result+self._mailbox_messages()))
            return self.activity_reply(result+self._mailbox_messages())
        return None

    def handle(self,event,request_sequence=None):
        if self.released or not self.application.registry.enabled(self.identity['id']):raise SessionOrderError('Account is offline or disabled')
        if self.social_overflow:raise SessionOrderError('Social consumer is too slow')
        if self.coop_error:raise SessionOrderError(self.coop_error)
        if self.application.dungeon_workers.isolated(self,event):
            result=self._dungeon_request(event,request_sequence)
            if result is not None:return result
            result=super().handle(event,request_sequence)
            # These native dungeon kinds cannot join/leave town, select a
            # character, trade or change appearance. Keep their exact domain
            # consumers and post-commit peer effects under the room's lock.
            from els_server.domain.elixir_flow import remember
            from els_server.domain.elixir_peer_sync import relay
            result=remember(self,result+self._mailbox_messages());relay(self)
            return result
        with self.application.world_lock:
            result=self._shared_request(event,request_sequence)
            if result is not None:
                from els_server.domain.friend_flow import synchronize as friend_sync
                return friend_sync(self,event,result)
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
            if acquired:
                with self.application.world_lock:leases.pop(self.identity['id'],None)
            raise
        with self.application.world_lock:
            return self._after_local(event,result)

    def _after_local(self,event,result):
        leases=self.application.playing
        if self.phase in ('closing','channels_ready') and leases.get(self.identity['id']) is self:
            self.application.world.leave_party(self)
            leases.pop(self.identity['id'],None)
        if event.event_id==0x202 and event.kind==0x113:
            from els_server.domain.apple_consumables import relay_committed_use
            relay_committed_use(self,result)
        if event.event_id==0x202 and event.kind in (0x2e8,0x2ec,0x432,0x42c,0x42f,0x2f5,0x2fb,0x8c7,0x219):
            from els_server.domain.companion_peer_sync import invalidate as invalidate_companion_peer
            invalidate_companion_peer(self)
        self.application.world.synchronize(self)
        if event.event_id==0x202 and event.kind in(0x4cb,0x219):
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
        from els_server.domain.elixir_flow import remember
        from els_server.domain.elixir_peer_sync import relay
        result=remember(self,result+self._mailbox_messages())
        relay(self)
        from els_server.domain.friend_flow import synchronize as friend_sync
        return friend_sync(self,event,result)

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

    def _clear_periodic_steps(self):
        pending=getattr(self,'_periodic_steps',None)
        if pending is not None:pending[1].close()
        self._periodic_steps=None;self._periodic_pending=False

    def periodic_notifications(self, *, _rooms=None, _slice=False):
        if not _slice:
            self._clear_periodic_steps();steps=self._friends_periodic_steps(_rooms)
            while True:
                try:next(steps)
                except StopIteration as done:return done.value
        if not self.application.registry.enabled(self.identity['id']):raise SessionOrderError('Account disabled')
        run=self.dungeon_run;account=self.account
        binding=(account,account.store,account.uid,self.shop_session_id,self.phase,
                 run,None if run is None else(run.run_id,run.stage,run.part,run.visits),
                 self.application.world.dungeons.room(self),
                 bool(getattr(self,'guild_agit',None)and self.guild_agit.get('revoked')))
        pending=getattr(self,'_periodic_steps',None)
        fresh=pending is None or pending[0]!=binding
        if fresh:
            self._clear_periodic_steps()
            # A changed actor/scene must not resume its predecessor's checks.
            if pending is not None:self.next_periodic=0
            pending=(binding,self._friends_periodic_steps(_rooms));self._periodic_steps=pending
        # Give the fast room poll its own turn, then coalesce adjacent quiet
        # checks within the existing four-millisecond periodic budget.
        deadline=time.monotonic()+.004
        try:
            while True:
                next(pending[1])
                if fresh or time.monotonic()>=deadline:break
        except StopIteration as done:
            self._periodic_steps=None;self._periodic_pending=False;return done.value
        except BaseException:
            self._clear_periodic_steps();raise
        self._periodic_pending=True
        return []

    def _friends_periodic_steps(self,_rooms):
        self.application.world.player_trades.periodic(self)
        self.application.world.racing.periodic(self)
        self.application.world.pvp.periodic(self)
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
        due=now>=self.next_periodic
        if due:self.next_periodic=now+1
        quiet=True
        if due and self._periodic_idle():yield
        if due:
            if self.application.world.dungeons.room(self) is None:messages=yield from self._local_periodic_steps()
            else:
                from els_server.domain.mount_flow import periodic as mount_periodic
                from els_server.domain.title_flow import periodic as title_periodic
                messages=self.expiration_notifications()
                quiet=not messages
                if quiet and self._periodic_idle():yield
                messages+=self._periodic_notifications()+mount_periodic(self)+title_periodic(self)
                quiet=quiet and not messages
                if quiet and self._periodic_idle():yield
                messages=self.activity_reply(messages)
            from els_server.domain.resonance_flow import synchronize as shared_resonance_sync
            messages=shared_resonance_sync(self,messages)
            quiet=quiet and not messages
            if quiet and self._periodic_idle():yield
            if self.phase=='town_ready':
                kinds={e.kind for e in messages if e.event_id==0x201}
                expiry=0x1c6 in kinds
                if 0x214 in kinds or expiry:self.application.world.appearance_changed(self)
            from els_server.domain.companion_peer_sync import receive as companion_peer_receive
            messages+=companion_peer_receive(self,now=now)
        from els_server.domain.elixir_flow import remember
        from els_server.domain.elixir_peer_sync import relay
        messages=remember(self,self._mailbox_messages()+messages)
        relay(self)
        return messages


    def release(self):
        self._clear_periodic_steps()
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
        from threading import RLock
        from els_server.economy import EconomyWorkers,WorldGate
        self.world_lock=RLock();self.world_gate=WorldGate();self.economy=EconomyWorkers(config.economy_workers)
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
        from els_server.dungeon_workers import DungeonWorkers
        self.dungeon_workers=DungeonWorkers(self)
        from els_server.realtime import RealtimeState
        self.realtime=RealtimeState()

    async def call(self, function, *args, **kwargs):
        submitted=time.perf_counter()
        session=getattr(function,'__self__',None)
        if type(session)is FriendsSession:
            async with self.economy.account_lock(session.identity['id']):
                return await self._dispatch(function,args,kwargs,submitted)
        return await self._dispatch(function,args,kwargs,submitted)

    async def _dispatch(self,function,args,kwargs,submitted):
        from els_server.performance import captured_calls
        from els_server.economy import DECLINED
        capture=captured_calls();queue_timing={}
        work=partial(self._worker_call,function,args,kwargs,submitted,capture,queue_timing)
        if self.dungeon_workers.candidate(function,args):
            queue_timing['lane']='dungeon'
            return await self.dungeon_workers.run(function.__self__,work,timing=queue_timing)
        if self.economy.candidate(function,args):
            queue_timing['lane']='economy'
            async with self.world_gate.parallel():
                result=await self.economy.queue.run(partial(self.economy.invoke,function.__self__,args[0],work),timing=queue_timing)
            if result is not DECLINED:return result
        from els_server.domain.dungeon_requests import priority_call
        queue_timing['lane']='world'
        async with self.world_gate.exclusive(dungeon=priority_call(function,args)):
            return await self.business_queue.run(work,timing=queue_timing)

    def _worker_call(self,function,args,kwargs,submitted,capture=None,queue_timing=None):
        from els_server.performance import captured_calls,worker_timing,request_category
        sample=dict(clock_before_ms=0.,domain_ms=0.,clock_after_ms=0.,after_reply_ms=0.,queue_ms=0.,admission_ms=0.,executor_ms=0.,batch_wait_ms=0.,handler_ms=0.,projection_ms=0.,projection_loads=0,projection_hits=0,registry_ms=0.,registry_checks=0,sql_begin_wait_ms=0.,sql_finish_wait_ms=0.,sql_finish_busy=0,sql_writer_held_ms=0.,sql_busy=0,sql_rollbacks=0,failed=True)
        def invoke():
            started=time.perf_counter();cpu_started=time.thread_time();sample['queue_ms']=(started-submitted)*1000
            sample['lane']=queue_timing.get('lane','world')if queue_timing is not None else'world'
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
                sample['worker_cpu_ms']=(time.thread_time()-cpu_started)*1000
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
            observed=activity and activity_due(function,args)
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
            from els_server.domain.session_auxiliary import maintenance_reply
            maintenance=(function.__name__=='handle' and len(args)==1
                         and maintenance_reply(session,args[0],result))
            flow=getattr(session,'activity2026_awards',None) if activity and (observed or result) and not maintenance else None
            after=getattr(flow,'after_reply',None)
            if after is None:return result
            started=time.perf_counter()
            try:return after(session,result)
            finally:sample['after_reply_ms']=(time.perf_counter()-started)*1000
        try:
            with self.dungeon_workers.worker_scope(function,args):
                if self.dungeon_workers.candidate(function,args)or self.economy.candidate(function,args):return invoke()
                with self.world_lock:return invoke()
        finally:
            if not (getattr(function,'__name__',None)=='periodic_notifications'and queue_timing is not None and 'batch_started_at'in queue_timing):
                self.dungeon_workers.publish(function,args,failed=sample['failed'],independent=self.dungeon_workers.candidate(function,args))


    async def periodic_batch(self,sessions):
        # At most one scheduler batch is queued. Each member retains an
        # independent committed-read scope and before/after activity clock.
        if len(sessions)>16:raise ValueError('Periodic batch bounds')
        submitted=time.perf_counter();queue_timing={}
        def invoke():
            queue_timing['batch_started_at']=time.perf_counter()
            try:
                rooms=set();result=[]
                for session in sessions:
                    options={'_rooms':rooms} if isinstance(session,FriendsSession) else {}
                    try:
                        messages=self._worker_call(session.periodic_notifications,(),options,submitted,queue_timing=queue_timing)
                        result.append((messages,None))
                    except Exception as error:result.append((None,error))
                return result
            finally:self.dungeon_workers.publish(invoke,(),periodic=True)
        async with self.world_gate.exclusive():
            return await self.business_queue.run(invoke,timing=queue_timing)

    def periodic_chunks(self,sessions,*,claims=None):
        from els_server.periodic_work import periodic_chunks
        return periodic_chunks(self,sessions,claims=claims)

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
                # Verify immutable economy definitions before the first reward writer.
                from els_server.domain.el_search_effects import catalog as collection_economy_catalog
                collection_economy_catalog()
                # Build immutable dungeon definitions before admitting the first player.
                from els_server.domain.dungeon_equipment_loot_rules import catalog as legacy_loot_catalog
                from els_server.domain.dungeon_loot_catalog import catalog as equipment_loot_catalog
                from els_server.domain.dungeon_material_loot_catalog import catalog as material_loot_catalog
                from els_server.domain.dungeon_source_loot import catalog as source_loot_catalog
                from els_server.domain.ordinary_misc_loot import catalog as misc_loot_catalog
                from els_server.domain.scene_actor_retirements import finite_sources
                from els_server.domain.normal_fatigue_rules import policy as fatigue_policy
                from els_server.domain.formal_npc_hp import policy as npc_hp_policy
                from els_server.domain.boss_npc_stats import policy as boss_stats_policy
                legacy_loot_catalog()
                equipment_loot_catalog()
                material_loot_catalog()
                source_loot_catalog()
                misc_loot_catalog()
                finite_sources()
                fatigue_policy()
                npc_hp_policy()
                boss_stats_policy()
                # Finish verified static readers and per-dungeon indices before player stores.
                from els_server.domain import (
                    elixir_economy, drop_pickup, equipment_economy, title_economy,
                    title_kill_rules, title_count_rules, title_clear_rules, title_bonus_counts,
                    title_essence, formal_npc_hp, random_mission_rules, local_artifact_rules,
                    native_line_triggers, raid_npc_stats, hot_time, resonance,
                    resonance_category_scroll, dungeon_population, summons, dungeon_spawns,
                    native_force_catalog, cooking_clear_materials, story_controller_retirements, known_resurrection_maps,
                    erp_potions_existing, environment_buff_flow, legacy_pve_exp, first_story_population,
                    mount_rules, instance_stats, native_hero_inputs, quick_bindings,
                    wisdom_potions, life_potions_existing, formal_raid_economy, character_stats,
                )
                elixir_economy.policy()
                drop_pickup.native_modes()
                equipment_economy.catalog()
                title_economy.effects()
                title_kill_rules.rules()
                title_count_rules.rules()
                title_clear_rules.rules()
                title_bonus_counts.effects()
                title_essence.rules()
                formal_npc_hp.raid_policy()
                random_mission_rules.policy()
                local_artifact_rules.policy()
                native_line_triggers.definitions()
                raid_npc_stats.policy()
                hot_time.policy()
                resonance.experience_multiplier()
                resonance.curve()
                resonance_category_scroll.scroll_items()
                dungeon_population._verified_population(0)
                dungeon_population._verified_population(1)
                dungeon_population._verified_population(2)
                native_force_catalog.by_skill()
                cooking_clear_materials.catalog()
                known_resurrection_maps.catalog()
                erp_potions_existing.definitions()
                environment_buff_flow.uniforms()
                legacy_pve_exp.policy()
                first_story_population.catalog()
                mount_rules.catalog()
                instance_stats.catalog()
                native_hero_inputs.policy()
                quick_bindings.mappings()
                wisdom_potions.definitions()
                life_potions_existing.definitions()
                formal_raid_economy.policy()
                character_stats._parameters()
                formal_raid_economy.circuits()
                title_economy.dungeon_types()
                # These immutable modules were first imported by native227.
                # Import only: all selected-actor reads/writes stay at arrival.
                from els_server import cleanup
                from els_server.domain import (
                    boosting_2026_region_entries, el_search_collection_quest,
                    tutorial_memory8_finale,
                )
                from els_server.storage import boosting_2026_gear_scroll_policy, challenge_scroll
                from els_server.domain.inventory_items import _item_wire_layout
                _item_wire_layout()
                # The observed first AD still imported these native consumers.
                # Build their static definitions before any player store opens.
                from els_server.domain import (
                    lithia_memory1_retirements, native_script_loot, public_controller_rules,
                )
                from els_server.storage import (
                    collection_synergy, elixir_economy as elixir_reward_store,
                    held_medals, legacy_pve_exp as legacy_experience_store,
                    ordinary_misc_loot as ordinary_misc_store,
                )
                held_medals.definitions()
                from els_server.domain.formal_npc_hp import ordinary_dungeon, initialization_factor
                for dungeon in sorted(map(int, npc_hp_policy()['maps'])):
                    ordinary_dungeon(dungeon)
                    initialization_factor(dungeon)
            from els_server.storage.game_schema import prepare
            from els_server.storage.characters import Characters
            prepare(self.config.state_file)
            Characters(self.config.state_file,1)
            from els_server.storage.game_mail import initialize as initialize_mail
            initialize_mail(self.config.state_file)
        self.account=await self.call(initialize)
        from els_server.storage.accounts import Accounts
        self.registry=await self.call(Accounts,self.config.accounts_file)
        from els_server.domain.selected_2026_friends import install as install_friends_activities
        await self.call(install_friends_activities,self)
        from els_server.domain.abyss_weapon_campaign import install as install_abyss_campaign
        await self.call(install_abyss_campaign,self)
        if self.config.profile=='integrated_dx11':
            # All source registrations are installed; build static shop views
            # before any listener accepts a player's first request for a role.
            from els_server.storage.shop_state import catalog as shop_catalog
            for unit_type in (None,*range(1,16)):
                await self.call(shop_catalog,unit_type)
        from els_server.domain.black_market_flow import run_application as market_runtime
        self._black_market_alive=True
        self._black_market_task=asyncio.create_task(market_runtime(self))

    def activity_options(self,account):
        return {'activity2026_awards':self.activity2026_awards_factory(account)} if self.activity2026_awards_factory is not None else {}

    async def session(self,port_probe_port=1,identity=None):
        if identity is None:raise SessionOrderError('Authentication required')
        def create():
            key=identity['id']
            account=self.accounts.get(key)  # Hold one strong root across construction/handoff.
            if account is None:
                from els_server.storage.characters import Characters
                roster=Characters(self.config.state_file,key)
                first=roster.first_identity()
                if first is not None:
                    account=LocalAccount(LocalState(self.config.state_file,first['uid']),key,identity['name'])
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
        def release_steps():
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
                lambda:self.world.field_bosses.detach(session),
                lambda:abandon_shadow(session), lambda:close_mount(session), local_flags,
                lambda:timer.observe(session,stop=True) if timer is not None else None,
                lambda:session.release() if isinstance(session,FriendsSession) else None)
        def release():
            with self.dungeon_workers.scope(session):return release_steps()
        release._dungeon_session=session
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
            self.dungeon_workers.close()
            self.economy.close()
            try:
                close=getattr(self.registry,'close',None)
                if close is not None:self.executor.submit(close).result()
            finally:
                self.executor.shutdown(wait=True,cancel_futures=True)
                self.preparation.close()
