"""Serialized business operations with local or authenticated account sessions."""
import asyncio
import time
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
            luciel=self.account.character()['unit_type']==10
            career=luciel and event.kind in (0x219,0x80f) and bool(kinds&{0x29f,0x59f})
            expiry=0x1c6 in kinds
            if event.kind in (0x104,0x213) or career or expiry or (event.kind in (0x4b1,0x6d7,0xad6) and any(e.kind==event.kind+1 and e.payload[:4]==bytes(4) for e in result)):
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

    def periodic_notifications(self):
        from els_server.domain.group_challenge import tick
        tick(self)
        self.application.world.field_bosses.periodic(self)
        if not self.application.registry.enabled(self.identity['id']):raise SessionOrderError('Account disabled')
        if self.social_overflow:raise SessionOrderError('Social consumer is too slow')
        self.application.world.dungeons.periodic(self)
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
        self.account=None
        self.registry=None;self.accounts={};self.playing={}
        from els_server.domain.friends_world import FriendsWorld
        self.world=FriendsWorld()

    async def call(self, function, *args, **kwargs):
        def invoke():
            from els_server.storage.read_scope import committed_reads
            with committed_reads():
                return invoke_with_reads()
        def invoke_with_reads():
            session=getattr(function,'__self__',None)
            timer=getattr(getattr(session,'activity2026_awards',None),'online',None)
            observed=isinstance(session,LocalSession) and function.__name__ in ('handle','periodic_notifications') and timer is not None
            if observed:timer.observe(session)
            try:
                result=function(*args,**kwargs)
            finally:
                if observed:timer.observe(session)
            flow=getattr(session,'activity2026_awards',None) if observed else None
            after=getattr(flow,'after_reply',None)
            return after(session,result) if after is not None else result
        return await asyncio.get_running_loop().run_in_executor(self.executor,invoke)

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

    def activity_options(self,account):
        return {'activity2026_awards':self.activity2026_awards_factory(account)} if self.activity2026_awards_factory is not None else {}

    async def session(self,port_probe_port=1,identity=None):
        if self.config.mode=='local':
            def create_local():
                session=LocalSession(self.account,port_probe_port=port_probe_port,**self.config.session_options(),**self.activity_options(self.account))
                # Dedicated reset witness; preserve generic local .application absence.
                session._chip_reset_local_application=self
                session._chip_reset_local_live=True
                return session
            return await self.call(create_local)
        if identity is None:raise SessionOrderError('Authentication required')
        def create():
            key=identity['id']
            if key not in self.accounts:
                from els_server.storage.characters import Characters
                roster=Characters(self.config.state_file,key)
                roles=roster.list()
                if roles:
                    account=LocalAccount(LocalState(self.config.state_file,roles[0]['uid']),key,identity['name'])
                else:
                    from els_server.domain.roster_account import RosterAccount
                    account=RosterAccount(self.config.state_file,key,identity['name'])
                account.enable_characters();self.accounts[key]=account
            return FriendsSession(self,identity,self.accounts[key],port_probe_port=port_probe_port,**self.config.session_options(),**self.activity_options(self.accounts[key]))
        return await self.call(create)

    async def release(self,session):
        from els_server.domain.mount_flow import close as close_mount
        def release():
            timer=getattr(getattr(session,'activity2026_awards',None),'online',None)
            try:
                from els_server.domain.tenebros_storage_flow import abandon as abandon_shadow
                try:
                    abandon_shadow(session)
                finally:
                    close_mount(session)
            finally:
                if type(session) is LocalSession and getattr(session,'_chip_reset_local_application',None) is self:
                    session._chip_reset_local_live=False
                try:
                    if timer is not None:timer.observe(session,stop=True)
                finally:
                    if isinstance(session,FriendsSession):session.release()
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
        self.executor.shutdown(wait=True,cancel_futures=True)
