"""Coordinated world operations and account-local economic workers."""
import asyncio
import time
from els_server.performance import OperationMetrics
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from contextlib import nullcontext
from contextvars import ContextVar
from els_server.domain.local_session import LocalAccount,LocalSession,SessionOrderError
from els_server.storage.local_state import LocalState

_town_move_wakes=ContextVar('town_move_wakes',default=None)


class FriendsSession(LocalSession):
    """One playable connection per account; frontend/channel handoffs may coexist."""
    def __init__(self,application,identity,account,**options):
        self.application=application;self.identity=identity;self.released=False
        self.position_writer=application.position_writer
        account.root._town_position_writer=application.position_writer
        self.coin_writer=application.coin_writer
        from els_server.domain.friends_world import Mailbox
        def pending(position_only=False):
            if getattr(self,'_realtime_town_moves',False)and position_only:
                wake=getattr(self,'_realtime_town_wake',None)
                if wake is not None:
                    pending_wakes=_town_move_wakes.get()
                    if pending_wakes is None:wake()
                    else:wake(pending_wakes)
                return
            notify=getattr(application,'periodic_notify',None)
            if notify is not None:notify(self)
        self.mailbox=Mailbox(pending);self.chat_times=deque();self.invite_times=deque();self.social_overflow=False
        self.next_periodic=0
        self._peer_drain_open=False
        self.coop_error=None
        super().__init__(account,**options)

    def _mailbox_messages(self):
        # A worker may now capture older member creations for its own reply.
        # Close peer bypass before draining; later coordinates wait for that
        # reply's original send/operation barrier.
        self._peer_drain_open=False
        messages=self.mailbox.drain()
        # A peer's committed guild departure can replace this actor's quest
        # list. Merge this recipient's account task through the same projector
        # used by ordinary own replies, after the sender's writer has ended.
        if self.activity2026_awards is not None and any(e.event_id==0x201 and e.kind==0x2b for e in messages):
            messages=self.activity2026_awards.finalize(self,messages)
        # Shared kills/clears commit the guest's EXP before queuing its AF/C1.
        # Auxiliary replies and not-yet-due upkeep can drain this queue without
        # activity_reply, so guide qualification belongs at this common exit.
        from els_server.domain.quest_flow import shared_updates
        messages+=shared_updates(self,messages)
        from els_server.domain.growth_guide_flow import synchronize as guide_sync
        messages=guide_sync(self,messages)
        from els_server.domain.achievement_flow import synchronize as achievement_sync
        return achievement_sync(self,None,messages)

    def activity_reply(self,replies):
        replies=self.activity2026_awards.finalize(self,replies) if self.activity2026_awards is not None else replies
        from els_server.domain.quest_flow import shared_updates
        replies+=shared_updates(self,replies)
        from els_server.domain.growth_guide_flow import synchronize as guide_sync
        from els_server.domain.elixir_flow import remember
        from els_server.domain.elixir_peer_sync import relay
        replies=remember(self,guide_sync(self,replies))
        relay(self)
        from els_server.domain.modern_ice_flow import synchronize as ice_sale_sync
        from els_server.domain.ariel_attendance_preview import project as reward_preview
        return reward_preview(self,ice_sale_sync(self,replies))

    def _shared_request(self,event,request_sequence,*,defer_solo_end=False):
        # The fixed DX11 capture's 7D0 is an unconsumed nine-byte auxiliary
        # notification, emitted five times a second. It has no domain handler.
        # Authentication and stream sequencing still run. The existing
        # independent periodic path performs online-clock persistence and
        # expiry/quest/activity work; never rebuild all wire projections here.
        from els_server.domain.elixir_flow import remember
        from els_server.domain.session_auxiliary import friends_auxiliary_noop
        if friends_auxiliary_noop(self,event):
            return remember(self,self._mailbox_messages())
        from els_server.domain.achievement_flow import handle as achievement_handle
        result=achievement_handle(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        from els_server.domain.social_settings_flow import handle as social_settings_handle
        result=social_settings_handle(self,event,request_sequence)
        if result is not None:return remember(self,result+self._mailbox_messages())
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
        from els_server.domain.wedding_flow import handle as wedding_handle
        result=wedding_handle(self,event,request_sequence)
        if result is not None:return remember(self,result+self._mailbox_messages())
        result=self.application.world.weddings.request(self,event,request_sequence)
        if result is not None:return remember(self,result+self._mailbox_messages())
        from els_server.domain.friend_flow import handle as friend_handle
        result=friend_handle(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.mentors.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.player_trades.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.pet_battles.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.racing.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.pvp.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        result=self.application.world.field_bosses.request(self,event,request_sequence)
        if result is not None:return self.activity_reply(result+self._mailbox_messages())
        # The caller retains the original account domain for an eligible solo
        # exit. Earlier shared handlers run here in their original order.
        if defer_solo_end:return None
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
        from els_server.dungeon_workers import KINDS
        # The shared router returns None for these kinds without a room.
        # Keep solo admission/handlers and all their original actor guards;
        # avoid reading an identity used only by a nonexistent shared result.
        if event.kind in KINDS and self.application.world.dungeons.room(self)is None:return None
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
        from els_server.domain.session_auxiliary import friends_auxiliary_noop
        if not(event.event_id==0x202 and event.kind==0x22b and self.phase=='town_ready')and not friends_auxiliary_noop(self,event):
            self.account.flush_position()
        if self.application.dungeon_workers.ordinary_town_move(self.handle,(event,)):
            result=super().handle(event,request_sequence)
            with self.application.world_lock:return self._after_local(event,result)
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
            from els_server.domain.achievement_flow import synchronize as achievement_sync
            return achievement_sync(self,event,result)
        own_end=(event.event_id==0x202 and event.kind==0x67
            and self.application.dungeon_workers.solo_transition(self.handle,(event,)))
        with self.application.world_lock:
            result=self._shared_request(event,request_sequence,defer_solo_end=own_end)
            if result is not None:return self._shared_reply(event,result)
        if own_end:
            from els_server.domain.luciel_native_end import handle as luciel_end_handle
            result=luciel_end_handle(self,event,request_sequence)
            if result is not None:
                with self.application.world_lock:
                    return self._shared_reply(event,self.activity_reply(result+self._mailbox_messages()))
        selecting=event.event_id==0x202 and event.kind==0x28
        entering_town=event.event_id==0x202 and event.kind==0x227 and self.phase=='square_accepted'
        own_town_input=entering_town and self.application.dungeon_workers.town_preparation(self.handle,(event,))
        leases=self.application.playing
        acquired=False
        if selecting:
            with self.application.world_lock:
                old=leases.get(self.identity['id'])
                if old is not None and old is not self:raise SessionOrderError('Account already playing')
                if old is None:leases[self.identity['id']]=self;acquired=True
        try:
            result=super().handle(event,request_sequence)
        except BaseException:
            if acquired:
                with self.application.world_lock:leases.pop(self.identity['id'],None)
            raise
        # This actor still owns its original account/domain and request read
        # scope. Its SQL projection is independent of other town membership.
        # Finish those reads before entering the shared membership lock.
        town_member=None
        if own_town_input and self.phase=='town_ready':
            town_member=(self.account.character(),self.account.get_location(),self.account.get_inventory_snapshot(equipped_only=True)['items'])
        with self.application.world_lock:
            result=self._after_local(event,result,town_member=town_member)
            # Successful arrival just completed the original full refresh.
            # Start its one-second upkeep interval here; duplicate227 in an
            # already-ready town cannot postpone the next observation.
            if entering_town and self.phase=='town_ready':
                self._town_entered_at=time.monotonic();self.next_periodic=max(self.next_periodic,self._town_entered_at+1)
            return result

    def _shared_reply(self,event,result):
        from els_server.domain.friend_flow import synchronize as friend_sync
        from els_server.domain.achievement_flow import synchronize as achievement_sync
        return self.application.world.mentors.synchronize(self,event,friend_sync(self,event,achievement_sync(self,event,result)))

    def _after_local(self,event,result,*,town_member=None):
        leases=self.application.playing
        if event.event_id==0x202 and event.kind==0x59a:
            self.application.world.mentors.reconcile(self.application)
        if self.phase in ('closing','channels_ready') and leases.get(self.identity['id']) is self:
            self.application.world.leave_party(self)
            leases.pop(self.identity['id'],None)
        if event.event_id==0x202 and event.kind==0x113:
            from els_server.domain.apple_consumables import relay_committed_use
            relay_committed_use(self,result)
        if event.event_id==0x202 and event.kind in (0x2e8,0x2ec,0x432,0x42c,0x42f,0x2f5,0x2fb,0x8c7,0x219):
            from els_server.domain.companion_peer_sync import invalidate as invalidate_companion_peer
            invalidate_companion_peer(self)
        self.application.world.synchronize(self,own=town_member)
        if event.event_id==0x202 and event.kind in(0x4cb,0x219):
            self.application.world.custom_changed(self,result)
        if self.phase=='town_ready' and event.event_id==0x202 and event.kind==0x22b:
            self.application.world.moved(self,event.payload)
        if self.phase=='town_ready' and event.event_id==0x202:
            kinds={e.kind for e in result if e.event_id==0x201}
            career=(event.kind in (0x219,0x80f) and bool(kinds&{0x29f,0x59f})
                    and self.account.character_identity()['unit_type']==10)
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
        from els_server.domain.achievement_flow import synchronize as achievement_sync
        return self.application.world.mentors.synchronize(self,event,friend_sync(self,event,achievement_sync(self,event,result)))

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

    def _periodic_idle(self):
        # Coalesced positions carry no local state dependency. They may be
        # delivered at a quiet boundary without draining an upkeep cycle.
        return super()._periodic_idle() or(self.phase=='town_ready'and not self.mailbox.messages)

    def periodic_notifications(self, *, _rooms=None, _slice=False, _mailbox_only=False):
        if _mailbox_only:
            if not self.application.registry.enabled(self.identity['id']):raise SessionOrderError('Account disabled')
            if self.social_overflow:raise SessionOrderError('Social consumer is too slow')
            if self.coop_error:raise SessionOrderError(self.coop_error)
            with self.application.world_lock:
                if not self.application.dungeon_workers.town_mailbox(self.periodic_notifications,()):return []
                from els_server.domain.elixir_flow import remember
                return remember(self,self._mailbox_messages())
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
        # A live dungeon room retains its fast first poll/two-ms budget.
        # Ordinary own-town upkeep coalesces more quiet reads per admission.
        town=self.application.dungeon_workers.town_periodic(self.periodic_notifications,())
        deadline=time.monotonic()+.002
        try:
            while True:
                next(pending[1])
                if(fresh and not town)or time.monotonic()>=deadline:break
        except StopIteration as done:
            self._periodic_steps=None;self._periodic_pending=False;return done.value
        except BaseException:
            self._clear_periodic_steps();raise
        self._periodic_pending=True
        if self.phase=='town_ready':
            with self.application.world_lock:
                # Committed peer notices need not wait for the remaining own
                # upkeep slices. Retain that generator and use its normal
                # recipient projector when draining the original queue.
                from els_server.domain.elixir_flow import remember
                return remember(self,self._mailbox_messages())
        return []

    def _friends_periodic_steps(self,_rooms):
        with self.application.world_lock if self.phase=='town_ready'else nullcontext():
            self.application.world.player_trades.periodic(self)
            self.application.world.mentors.expire()
            self.application.world.racing.periodic(self)
            self.application.world.pet_battles.periodic(self)
            self.application.world.pvp.periodic(self)
            self.application.world.weddings.periodic(self)
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
        # Native selection/scene initialization already performs its complete
        # refresh. Keep shared-room polling, clocks and mailbox delivery while
        # loading; own gameplay upkeep starts when its scene is active.
        active=self.role=='game'and(self.phase in('town_ready','guild_agit_ready')or(self.phase=='dungeon_active'and self.dungeon_substage_synced))
        quiet=True
        if due and active and self._periodic_idle():yield
        if due and active:
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
            from els_server.domain.achievement_flow import synchronize as achievement_sync
            messages=achievement_sync(self,None,messages)
            quiet=quiet and not messages
            if quiet and self._periodic_idle():yield
            if self.phase=='town_ready':
                kinds={e.kind for e in messages if e.event_id==0x201}
                expiry=0x1c6 in kinds
                if 0x214 in kinds or expiry:
                    with self.application.world_lock:self.application.world.appearance_changed(self)
            from els_server.domain.companion_peer_sync import receive as companion_peer_receive
            # A cooperative cycle can resume in a later second. Its old
            # start timestamp would rewind the shared peer-read cache epoch
            # and reload every nearby actor for each resumed receiver.
            with self.application.world_lock if self.phase=='town_ready'else nullcontext():
                messages+=companion_peer_receive(self,now=time.monotonic())
        from els_server.domain.elixir_flow import remember
        from els_server.domain.elixir_peer_sync import relay
        with self.application.world_lock if self.phase=='town_ready'else nullcontext():
            messages=remember(self,self._mailbox_messages()+messages)
            relay(self)
        if due and active:
            self._upkeep_cycles=getattr(self,'_upkeep_cycles',0)+1
            self._upkeep_completed_at=time.monotonic()
        return messages


    def release(self):
        self._clear_periodic_steps()
        try:
            try:self.account.flush_position()
            finally:self.application.world.disconnect(self)
        finally:
            owner=self.application.playing.get(self.identity['id']) is self
            if owner:self.application.playing.pop(self.identity['id'])
            self.released=True
            from els_server.domain.companion_peer_sync import invalidate
            invalidate(self);self.companion_peer_projection=None
            # These sources have already retired under the actor/domain lock.
            # Do not leave a closed actor's graph in caches or owner cycles.
            self.mailbox.on_pending=None
            hp_context=getattr(self,'_c1_hp_context',None)
            if hp_context is not None:hp_context.run=None
            self._c1_hp_context=None;self._normal_fatigue_origin=None;self._random_mission_origin=None
            self._environment_entry=None;self.dungeon_run=None;self.world_drops={}
            if owner:self.position_writer.forget(self.account.uid)


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
        from els_server.storage.read_scope import ReadConnections
        self.read_connections=ReadConnections()
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
        from els_server.storage.wal_checkpoints import WALCheckpoints
        self.checkpoints=WALCheckpoints(config.state_file)
        from els_server.storage.position_writer import PositionWriter
        self.position_writer=PositionWriter(config.state_file,checkpoints=self.checkpoints)
        from els_server.storage.coin_writer import CoinWriter
        self.coin_writer=CoinWriter(config.state_file,checkpoints=self.checkpoints)
        from els_server.storage.death_writer import DeathWriter
        self.death_writer=DeathWriter(config.state_file,self.read_connections,checkpoints=self.checkpoints)
        from els_server.storage.clock_writer import ClockWriter
        self.clock_writer=ClockWriter(config.state_file,checkpoints=self.checkpoints)

    async def call(self, function, *args, **kwargs):
        submitted=time.perf_counter()
        session=getattr(function,'__self__',None)
        # A queued ordinary move has not captured this connection's mailbox.
        # Allow peers through while waiting for account/executor admission;
        # the original worker closes the window before capturing creations.
        peer_window=self.dungeon_workers.ordinary_town_move(function,args)
        if peer_window:session._peer_drain_open=True
        try:
            if type(session)is FriendsSession:
                async with self.economy.account_lock(session.identity['id']):
                    return await self._dispatch(function,args,kwargs,submitted)
            return await self._dispatch(function,args,kwargs,submitted)
        finally:
            if peer_window:session._peer_drain_open=False

    async def _dispatch(self,function,args,kwargs,submitted):
        self.checkpoints.check()
        from els_server.performance import captured_calls
        from els_server.economy import DECLINED
        capture=captured_calls();queue_timing={}
        work=partial(self._worker_call,function,args,kwargs,submitted,capture,queue_timing)
        if self.dungeon_workers.candidate(function,args):
            queue_timing['lane']='dungeon'
            if self.dungeon_workers.town_periodic(function,args)and not kwargs.get('_mailbox_only',False):
                queue_timing['lane']='town'
                return await self.dungeon_workers.run_upkeep(function.__self__,work,timing=queue_timing)
            transition=self.dungeon_workers.solo_transition(function,args)
            own_preparation=self.dungeon_workers.town_preparation(function,args)or transition
            preparation=own_preparation and(transition or args[0].kind in(0x28,0x227,0x485))
            movement=not own_preparation and self.dungeon_workers.town_movement(function,args)
            queue_timing['town_movement']=movement
            town=own_preparation or movement
            if town:queue_timing['lane']='town'
            pickup=not town and bool(args) and args[0].kind==0xd0
            return await self.dungeon_workers.run(function.__self__,work,timing=queue_timing,town=town,pickup=pickup,death=self.dungeon_workers.death_waiter(function,args),preparation=preparation,selection=preparation and args[0].kind==0x28)
        if self.economy.candidate(function,args):
            queue_timing['lane']='economy'
            async with self.economy.worker_admission:
                async with self.world_gate.parallel():
                    result=await self.economy.queue.run(partial(self.economy.invoke,function.__self__,args[0],work),timing=queue_timing)
            if result is not DECLINED:return result
        from els_server.domain.dungeon_requests import priority_call
        queue_timing['lane']='world'
        async with self.world_gate.exclusive(dungeon=priority_call(function,args)):
            return await self.business_queue.run(work,timing=queue_timing)

    def _worker_call(self,function,args,kwargs,submitted,capture=None,queue_timing=None):
        worker_entered=time.perf_counter()
        pending_wakes={}if queue_timing is not None and queue_timing.get('town_movement')else None
        wake_token=None
        if queue_timing is not None:queue_timing.setdefault('batch_started_at',worker_entered)
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
                session=getattr(function,'__self__',None)
                if type(session)is FriendsSession:
                    from els_server.periodic_work import next_poll_deadline
                    session._periodic_due=next_poll_deadline(self,session,time.monotonic())
                sample['handler_ms']=(time.perf_counter()-started)*1000
                sample['worker_cpu_ms']=(time.thread_time()-cpu_started)*1000
                self.performance.record(getattr(function,'__name__','other'),sample,request=request)
                if capture is not None:capture.append(dict(sample))
        def invoke_scoped():
            from els_server.storage.read_scope import committed_reads
            with committed_reads(connections=self.read_connections):
                result=invoke_with_reads()
                session=getattr(function,'__self__',None)
                if type(session)is FriendsSession and function.__name__ in ('handle','periodic_notifications'):
                    from els_server.domain.dungeon_result_stats import finalize
                    result=finalize(session,result)
                return result
        def invoke_with_reads():
            from els_server.domain.session_auxiliary import auxiliary_call,activity_due
            if auxiliary_call(function,args):
                started=time.perf_counter()
                try:return function(*args,**kwargs)
                finally:sample['domain_ms']=(time.perf_counter()-started)*1000
            session=getattr(function,'__self__',None)
            timer=getattr(getattr(session,'activity2026_awards',None),'online',None)
            activity=isinstance(session,LocalSession) and function.__name__ in ('handle','periodic_notifications') and timer is not None
            observe_clock=(getattr(timer,'observe_background',timer.observe)if function.__name__=='periodic_notifications'else timer.observe)if activity else None
            observed=activity and not kwargs.get('_mailbox_only',False)and activity_due(function,args)
            if observed:
                started=time.perf_counter()
                try:observe_clock(session)
                finally:sample['clock_before_ms']=(time.perf_counter()-started)*1000
            started=time.perf_counter()
            try:
                result=function(*args,**kwargs)
            finally:
                sample['domain_ms']=(time.perf_counter()-started)*1000
                if observed:
                    started=time.perf_counter()
                    try:observe_clock(session)
                    finally:sample['clock_after_ms']=(time.perf_counter()-started)*1000
            from els_server.domain.session_auxiliary import maintenance_reply,town_peer_reply
            maintenance=(function.__name__=='handle' and len(args)==1
                         and maintenance_reply(session,args[0],result))
            if (not observed and function.__name__=='periodic_notifications'
                    and type(session)is FriendsSession and session.phase=='town_ready'
                    and result and town_peer_reply(result)):
                maintenance=True
            flow=getattr(session,'activity2026_awards',None) if activity and (observed or result) and not maintenance else None
            after=getattr(flow,'after_reply',None)
            if after is None:return result
            # A sliced notification can resume after another member's shared
            # reward levels this actor. Refresh the existing clock before its
            # mail/display projection when that slice emits a real response.
            if not observed and (not(function.__name__=='handle'and not activity_due(function,args,after=True))
                    or(function.__name__=='handle'and len(args)==1 and args[0].kind==0x9e)):
                started=time.perf_counter()
                try:observe_clock(session)
                finally:sample['clock_after_ms']=(time.perf_counter()-started)*1000
            started=time.perf_counter()
            try:return after(session,result)
            finally:sample['after_reply_ms']=(time.perf_counter()-started)*1000
        peer_session=getattr(function,'__self__',None)
        peer_window=(type(peer_session)is FriendsSession and peer_session.phase=='town_ready'
            and(function.__name__=='periodic_notifications' or self.dungeon_workers.ordinary_town_move(function,args)))
        if peer_window:peer_session._peer_drain_open=True
        try:
            if pending_wakes is not None:wake_token=_town_move_wakes.set(pending_wakes)
            with self.dungeon_workers.worker_scope(function,args):
                sample['scope_wait_ms']=(time.perf_counter()-worker_entered)*1000
                if self.dungeon_workers.candidate(function,args)or self.economy.candidate(function,args):return invoke()
                with self.world_lock:return invoke()
        finally:
            if peer_window:peer_session._peer_drain_open=False
            try:
                if not (getattr(function,'__name__',None)=='periodic_notifications'and queue_timing is not None and 'batch_started_at'in queue_timing):
                    self.dungeon_workers.publish(function,args,failed=sample['failed'],independent=self.dungeon_workers.candidate(function,args))
            finally:
                if wake_token is not None:
                    _town_move_wakes.reset(wake_token)
                    # A producer held world while appending to peer mailboxes.
                    # Wake their socket loops only after publication released it.
                    def notify(events):
                        for event in events:event.set()
                    # One cross-thread IOCP wake per listener loop, instead of
                    # one kernel wake for every recipient of the same move.
                    for loop,events in pending_wakes.items():loop.call_soon_threadsafe(notify,tuple(events))


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
        try:
            async with self.world_gate.exclusive():
                return await self.business_queue.run(invoke,timing=queue_timing)
        finally:invoke=None

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
                legacy_pve_exp.reference_policy()
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
                from els_server.domain import guild_rules,guild_quests
                guild_rules.catalog();guild_quests.catalog()
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
                from els_server.storage.seal_quests import collection_quest_ids
                collection_quest_ids()
                from els_server.domain.hunter_chest_rules import _positions as hunter_positions
                hunter_positions()
                from els_server.domain.hunter_sphere_rules import definitions as hunter_sphere_definitions
                hunter_sphere_definitions()
                # These read-only town consumers were first compiled during
                # initial upkeep. Import before listening; no actor projection
                # or player write is performed by this preparation.
                from els_server.domain import companion_peer_sync,flask_flow,server_announcements
                # Actual first B3 still compiled these six modules on a live
                # actor. Their imports contain definitions only; no player
                # projection or write belongs in startup preparation.
                from els_server.domain import hunter_chest_flow,devildom1_raid2_controllers
                from els_server.protocol import npc_uid_map,hunter_chest_messages
                from els_server.storage import hunter_chest,title_kills
                from els_server.domain import guild_effects
                from els_server.storage import guild_economy
                from els_server.protocol.dungeon_messages import _member_layout
                _member_layout()
                from els_server.storage import (
                    flask as flask_storage,manufacture,tenebros_storage,
                    account_cartridge_registration,pet_support_periods,
                )
                server_announcements.policy()
                from els_server.domain.formal_npc_hp import ordinary_dungeon, initialization_factor
                for dungeon in sorted(map(int, npc_hp_policy()['maps'])):
                    ordinary_dungeon(dungeon)
                    initialization_factor(dungeon)
            from els_server.storage.game_schema import prepare
            from els_server.storage.characters import Characters
            prepare(self.config.state_file)
            from contextlib import closing
            import sqlite3
            from els_server.storage.achievement_history import ensure_indexes as prepare_achievement_indexes
            from els_server.storage.sqlite_timing import write_transaction
            with closing(sqlite3.connect(self.config.state_file,timeout=10))as db,write_transaction(db):
                prepare_achievement_indexes(db)
            Characters(self.config.state_file,1)
            from els_server.storage.master_presets import repair as repair_master_presets
            repair_master_presets(self.config.state_file)
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
            from els_server.storage.inventory_state import prepare_saved_inventories
            await self.call(prepare_saved_inventories,self.config.state_file)
            # All source registrations are installed; build static shop views
            # before any listener accepts a player's first request for a role.
            from els_server.storage.shop_state import catalog as shop_catalog
            for unit_type in (None,*range(1,16)):
                await self.call(shop_catalog,unit_type)
        await self.call(self.checkpoints.prepare)
        await self._prepare_workers()
        from els_server.domain.black_market_flow import run_application as market_runtime
        self._black_market_alive=True
        self._black_market_task=asyncio.create_task(market_runtime(self))

    async def _prepare_workers(self):
        def prepare_modules():
            # These current guild/studio dispatchers were still compiled by
            # the first native login. Their imports contain no actor work.
            from els_server.domain import guild_system_flow,guild_banner_flow,guild_recruit,photo_zone_flow
            from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,encode_frame,decode_frame
            from els_server.protocol.local_messages import _character_unit_layout
            _character_unit_layout()
            # Construct both native cipher directions before opening a socket.
            # This private frame has no connection, sequence state or recipient.
            warmup=b'ELS native startup'
            frame=encode_frame(warmup,BOOTSTRAP_KEYS,iv=bytes(8))
            if decode_frame(frame,BOOTSTRAP_KEYS,expected_sequence=1).plaintext!=warmup:
                raise ValueError('Native startup codec preparation failed')
            # These modules were first compiled by real native login/roster/town
            # requests. Import after activity installation and before listeners;
            # actor reads, handlers and writers still execute on their own paths.
            from els_server.domain import (
                anvil_flow, anvil_rules, ariel_attendance_flow, ariel_attendance_mark,
                ariel_attendance_preview, artifact_flow, assembly_flow, avatar_set_flow,
                bag_expansion_flow, bank_view_flow, black_market_box_flow, board_ranking_flow,
                boosting_2026_buff, cartridge_exchange_flow, cartridge_recipe679_flow, cartridge_recipe679_rules,
                challenge_flow, challenge_scroll, character_lifecycle_flow, character_selection_flow,
                chip_circuit_transfer_flow, companion_flow, coupon_flow, dungeon_hp_c1,
                dungeon_native_actions, dungeon_settlement_commands, el_search_collection_flow, el_search_collection_tickets,
                el_shard_flow, el_shard_identification_flow, elixir_flow, elixir_peer_sync,
                ep_conversion, ep_conversion_flow, ep_guardian_necklaces, ep_shop,
                ep_shop_flow, epic_skip, equipment_cartridge_flow, equipment_chip_flow,
                equipment_circuit_flow, equipment_reforge_flow, equipment_reforge_transfer_flow, equipment_spell_exchange_flow,
                equipment_tuning, equipment_ui_flow, erp_potion_flow, exascale_color_flow,
                feta_exchange_flow, feta_exchange_rules, feta_gauge_flow, feta_limit_flow,
                field_travel, first_story_entry, fish_exchange_flow, fishing_attempt,
                fishing_village1500, fishing_vip_flow, friends_spawns, furniture_flow,
                group_challenge, growth_guide_flow, guidebook_flow, guild_agit_flow,
                guild_coin_flow, guild_initial_profile, guild_license_flow, guild_membership_flow,
                housing_access_flow, housing_layout_flow, housing_room_flow, known_resurrection_flow,
                local_bootstrap_clock, luciel_native_end, luciel_native_status, luciel_state,
                mail_flow, mailbox_extras, mainline_find_npc, manufacture_flow,
                market_conversion_flow, modern_ice_flow, modern_synthesis_flow, mount_flow,
                mount_racing_exchange_flow, mount_racing_selection, mount_reset_flow, native_force_exchange_flow,
                neblon_role_change_flow, normal_fatigue_flow, online_clock_transaction, option_conversion_existing_flow,
                paid_enhancement, party_recruitment, pending_part_end, pet_actions,
                pet_expedition_flow, pet_nutrition_flow, pet_progression_flow, pet_support_flow,
                player_mail_flow, profession_growth, promotion_reward_flow, purifier_exchange_flow,
                pve_economy_flow, pvp_material_exchange_flow, pvp_specialization_flow, quest_flow,
                quick_start_flow, raid_life_observation, raid_reward_flow, random_mission_flow,
                regional_material_exchange_flow, relationship_flow, reselection_flow, resonance_flow,
                resonance_page_expansion_flow, resonance_period_flow, rosso_reset, roster_account,
                session_dispatch, silver_mirror_flow, skill_page_shop_flow, skill_trait_reset,
                skill_trait_reset_flow, spell_socket_flow, tenebros_capacity_flow, tenebros_conversion_flow,
                tenebros_identification_flow, tenebros_storage_flow, title_flow, title_level_rules,
                town_travel, town_travel_flow, trade_board_authority, trade_board_flow,
                tutorial_progression, weapon_growth_flow, white_armor_flow, white_armor_rules,
                white_chip_decomposition_flow,
            )
            from els_server.storage import (
                account_key_bindings, anvil, ariel_attendance, ariel_cash,
                ariel_daily_special, assembly_state, avatar_sets, bank_view,
                boosting_2026_limited_pet, career_purchase_recovery, career_shop, careers,
                cartridge_exchange, cartridge_recipe679, challenge_group, challenge_state,
                character_selection, companion_receipt_inventory, companion_state, ep_conversion,
                ep_shop, epic_followups, equipment_circuits, equipment_restoration,
                feta_exchange_weekly, fish_exchange, fishing_attempt, fishing_vip,
                growth_guide, guidebook, housing_access, housing_layouts,
                housing_rooms, known_resurrection, luciel_state, master_presets,
                material_exchange, modern_ice, native_force_exchange, paid_enhancement,
                pet_expedition, pet_progression, pet_support, purifier_exchange,
                quick_slots, raid_reward_actions, random_missions, resurrection_counter,
                title_clears, title_counts, title_levels, trade_board_state,
                world_elixirs,
            )
            from els_server.protocol import (
                anvil_messages, ariel_attendance_messages, ariel_daily_special_messages, artifact_socket_messages,
                assembly_messages, avatar_set_messages, bag_expansion_messages, bank_view_messages,
                board_ranking_messages, cartridge_recipe679_messages, challenge_messages, character_lifecycle_messages,
                character_selection_messages, chip_circuit_transfer_messages, content_count_messages, cube_messages,
                el_shard_identification_messages, el_shard_messages, ep_conversion_messages, ep_shop_messages,
                equipment_circuit_messages, equipment_reforge_transfer_messages, equipment_restoration_messages, equipment_spell_exchange,
                exascale_color_messages, expiration_messages, feta_exchange_messages, feta_limit_messages,
                fish_exchange_messages, fishing_messages, fishing_vip_messages, growth_guide_messages,
                guidebook_messages, guild_agit_messages, guild_coin_messages, guild_membership_profile,
                housing_access_messages, housing_layout_messages, housing_messages, ice_messages,
                luciel_messages, mail_attachment_messages, mail_messages, mailbox_extras,
                market_conversion_messages, modern_ice_messages, modern_synthesis_messages, neblon_role_change_messages,
                option_conversion_existing_messages, paid_enhancement_messages, party_recruitment_messages, pet_expedition_messages,
                pet_progression_messages, pet_support_messages, player_mail_messages, purifier_exchange_messages,
                quick_start_messages, raid_economy_protocol, random_mission_messages, session_clock,
                spell_socket_messages, tenebros_conversion_messages, tenebros_identification_messages, town_travel_messages,
                trade_board_messages, wardrobe_messages, weapon_growth_messages, weekly_dungeon_counts,
                world_buff_messages,
            )
            # Current achievement resources and the observed late AD import
            # are immutable. Prepare them before listening, without projecting
            # an actor or opening another player transaction.
            from els_server.domain import achievement_flow
            from els_server.domain.achievement_catalog import catalog as achievement_catalog,rewards as achievement_rewards
            from els_server.storage import achievement_history,achievement_profiles,erp_support_quest_scope
            achievement_catalog();achievement_rewards()
        await self.call(prepare_modules)
        from threading import Barrier
        from els_server.storage.read_scope import committed_reads,snapshot_connection
        # Establish the registry's primary handle on its owning account worker
        # first. Other workers get their own read-only, autocommit handles.
        await self.call(self.registry.enabled,0)
        loop=asyncio.get_running_loop()
        def prepare_reads():
            with committed_reads(connections=self.read_connections):
                with snapshot_connection(self.config.state_file)as db:
                    db.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone()
                with snapshot_connection(self.config.accounts_file)as db:
                    db.execute('SELECT id,name,enabled FROM accounts ORDER BY id').fetchall()
                self.registry.enabled(0)
        for executor,count in ((self.executor,1),(self.economy.executor,self.economy.workers),
                (self.dungeon_workers.executor,self.dungeon_workers.workers),(self.dungeon_workers.pickup_executor,self.dungeon_workers.pickup_workers),(self.dungeon_workers.upkeep_executor,self.dungeon_workers.upkeep_workers),
                (self.dungeon_workers.death_executor,self.dungeon_workers.death_workers),
                (self.dungeon_workers.town_upkeep_executor,self.dungeon_workers.town_upkeep_workers),
                (self.dungeon_workers.town_executor,self.dungeon_workers.town_workers)):
            ready=Barrier(count)
            def prepare(ready=ready):
                # Starting every worker now also prepares each worker's SQL
                # statements; no actor projection or read transaction survives.
                ready.wait()
                prepare_reads()
            pending=[]
            try:
                for _ in range(count):pending.append(loop.run_in_executor(executor,prepare))
                await asyncio.gather(*pending)
            finally:
                # A failed thread creation leaves fewer participants than
                # the barrier requires. Release and join the submitted work
                # before startup reports that failure or closes its pools.
                ready.abort()
                await asyncio.gather(*pending,return_exceptions=True)
        await loop.run_in_executor(self.executor,self.coin_writer.prepare)
        await loop.run_in_executor(self.executor,self.death_writer.prepare,prepare_reads)
        await loop.run_in_executor(self.executor,self.clock_writer.prepare)

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
                market=getattr(self,'_black_market_sessions',None)
                key=(session.account.uid,session.shop_session_id)
                if market is not None and market.get(key)is session:market.pop(key)
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
            # The socket still owns this cleanup until its real worker retires.
            # Otherwise shutdown can close admission before release even starts.
            while not cleanup.done():
                try:await asyncio.shield(cleanup)
                except asyncio.CancelledError:continue
                except BaseException:break
            raise

    def close(self):
        # Running SQL is allowed to commit/rollback before releasing save ownership.
        self._black_market_alive=False
        task=getattr(self,'_black_market_task',None)
        if task is not None:task.cancel()
        if not self._executor_closed:
            self._executor_closed=True
            from els_server.cleanup import cleanup_all
            def close_registry():
                close=getattr(self.registry,'close',None)
                if close is not None:self.executor.submit(close).result()
            # A failed final save must not leave the remaining non-daemon
            # writers alive. Retire every resource in the original order,
            # then preserve all failures through the existing cleanup helper.
            cleanup_all(self.business_queue.close,self.dungeon_workers.close,
                self.economy.close,close_registry,
                lambda:self.executor.shutdown(wait=True,cancel_futures=True),
                self.position_writer.close,self.coin_writer.close,
                self.death_writer.close,self.clock_writer.close,
                self.preparation.close,self.checkpoints.close,self.read_connections.close)
