"""Completed-worker routing views; no game database work in the data path."""
import asyncio,json,time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from types import MappingProxyType
from els_server.domain.dungeon_time_sync import context
from els_server.protocol.protocol_codec import Event

LEGACY=object()
PENDING=object()
EMPTY=b'\1null'

@dataclass(frozen=True)
class View:
    manifests:object
    routes:object
    clocks:object
    required:object
    bindings:object
    auxiliary:object
    legacy:frozenset

def empty():return View(*[MappingProxyType({})for _ in range(6)],frozenset())

class RealtimeState:
    def __init__(self):self.view=empty();self.next_periodic=0.;self.published=0;self.last_state=None;self.state_rows={}
    def transport_state(self,app,*,exclude=frozenset()):
        rows=[]
        previous={r[0]:r for r in self.last_state or ()}
        for account,s in app.playing.items():
            if account in exclude:
                if account in previous:rows.append(previous[account])
                continue
            rows.append(self.transport_row(app,account,s))
        return tuple(rows)
    def transport_row(self,app,account,s):
        from els_server.domain.equipment_chip_flow import current_lease
        d=app.world.dungeons;r=d.room(s)
        room=(id(r),r.seed,r.phase,r.party.get('run')is r,app.world.party_of.get(s)is r.party,
            s in r.party['members'],tuple(id(m)for m in r.members),tuple(id(m)for m in r.party['members']),
            tuple(d.transport_room(m)is r for m in r.members))if r is not None else None
        photo=getattr(s,'photo_zone',None)
        photo=None if photo is None else photo['room']
        photo_state=None if photo is None else (id(photo),photo['epoch'],tuple((id(p),photo['ports'][p])for p in photo['members']))
        wedding=app.world.weddings.room(s)
        wedding_state=None if wedding is None else app.world.weddings.signature(wedding)
        return (account,id(s),s.account.uid,current_lease(s),s.role,s.phase,s.released,s.coop_error,s.social_overflow,s.client_build,
            s.enter_dungeon,s.dungeon_return_pending,s.reward_run_id,getattr(s,'dungeon_participants',None),context(s),room,
            id(app.world.pvp.room(s)),id(app.world.field_bosses.room(s)),photo_state,wedding_state)

    def unchanged_scope(self,app,members):
        # Called under world and this domain's nonblocking acquired lock.
        # Only periodic polls and completed AD/D0 may reuse this exact view.
        # A changed routing fact publishes before the original 100ms deadline.
        if time.monotonic()>=self.next_periodic or len(self.state_rows)!=len(app.playing):return False
        for s in members:
            account=s.identity['id']
            if app.playing.get(account)is not s or self.state_rows.get(account)!=self.transport_row(app,account,s):return False
        return True

    def publish(self,app,function,args,*,failed=False,periodic=False,exclude=frozenset()):
        if app.config.mode!='friends'or app.registry is None:return
        name=getattr(function,'__name__','')
        if not failed and name in('manifest','relay_target'):return
        if not failed and name=='handle'and args and isinstance(args[0],Event):
            event=args[0]
            if event.event_id in(0,0x402) or(event.event_id==0x202 and event.kind==0x7d0):return
        now=time.monotonic()
        try:
            state=self.transport_state(app,exclude=exclude)
            if not failed and (periodic or name=='periodic_notifications')and now<self.next_periodic and state==self.last_state:return
            old=self.view
            manifests={k:v for k,v in old.manifests.items()if k in exclude}
            routes={k:v for k,v in old.routes.items()if k[0]in exclude}
            clocks={k:v for k,v in old.clocks.items()if v[0]in exclude}
            required={k:v for k,v in old.required.items()if k in exclude}
            bindings={k:v for k,v in old.bindings.items()if k in exclude}
            auxiliary={k:v for k,v in old.auxiliary.items()if v in exclude}
            legacy=set(old.legacy&exclude);dungeons=app.world.dungeons
            from els_server.domain.session_auxiliary import friends_auxiliary_session
            # Reuse all original authorization predicates against one committed
            # account-registry read. No enabled result escapes this worker scope.
            with app.registry.enabled_snapshot():
                for account,session in app.playing.items():
                    if account in exclude:continue
                    bindings[account]=session.shop_session_id
                    room=dungeons.room(session)
                    members=[s for s in room.members if room.phase!='clear'or dungeons.room(s)is room]if room is not None else[session]
                    photo=getattr(session,'photo_zone',None)
                    if photo is not None and photo['room']is not None:members=photo['room']['members']
                    wedding=app.world.weddings.room(session)
                    if wedding is not None:members=tuple(wedding.members)
                    required[account]=tuple(s.account.account_id for s in members)
                    if not app.registry.enabled(account):continue
                    if app.world.pvp.room(session)is not None or app.world.field_bosses.room(session)is not None:
                        legacy.add(account);continue
                    if (not session.released and not session.social_overflow and not session.coop_error
                            and friends_auxiliary_session(session)):
                        auxiliary[session.shop_session_id]=account
                    key=context(session)
                    if key is not None and not session.released and not session.coop_error:
                        from els_server.domain.equipment_chip_flow import current_lease
                        if current_lease(session):clocks[session.shop_session_id]=(account,key)
                    manifest=dungeons.manifest(app,account)
                    if manifest is None:continue
                    manifests[account]=b'\1'+json.dumps(manifest,separators=(',',':')).encode()
                    for peer in manifest['peers']:
                        route=dungeons.relay_target(app,account,manifest['epoch'],peer['uid'])
                        if route is not None:routes[account,manifest['epoch'],peer['uid']]=route
            self.view=View(*[MappingProxyType(m)for m in(manifests,routes,clocks,required,bindings,auxiliary)],frozenset(legacy))
        except BaseException:
            self.view=empty();raise
        self.next_periodic=now+.1;self.published+=1;self.last_state=state;self.state_rows={row[0]:row for row in state}

class RealtimeAccess:
    """One registry reader for the listener, independent of the asset worker."""
    def __init__(self,app,log):
        self.app=app;self.log=log;self.enabled=frozenset();self.checked=0.;self.task=None;self.closed={};self.lost_relays={}
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='els-realtime-auth')
    async def refresh(self):
        def read():return self.app.registry.list(),time.monotonic()
        rows,checked=await asyncio.get_running_loop().run_in_executor(self.executor,read)
        self.enabled=frozenset(r['id']for r in rows if r['enabled']);self.checked=checked
        registered={r['id']for r in rows};self.closed={a:s for a,s in self.closed.items()if a in registered or a in self.app.realtime.view.bindings}
        self.lost_relays={a:s for a,s in self.lost_relays.items()if a in registered or a in self.app.realtime.view.bindings}
    async def start(self):
        await self.refresh()
        async def poll():
            while True:
                await asyncio.sleep(.1);await self.refresh()
        self.task=asyncio.create_task(poll(),name='realtime-account-registry')
        def done(task):
            if not task.cancelled()and task.exception():
                self.enabled=frozenset();self.log('realtime_registry_failed',error=type(task.exception()).__name__)
        self.task.add_done_callback(done)
    def denial(self,account,view):
        for member in view.required.get(account,(account,)):
            if member in self.closed and self.closed[member]==view.bindings.get(member):return 'session_closed'
            if member in self.lost_relays and self.lost_relays[member]==view.bindings.get(member):return 'relay_lost'
        if self.task is not None and self.task.done() and not self.task.cancelled() and self.task.exception() is not None:
            return 'registry_reader_failed'
        if time.monotonic()-self.checked>.5:return 'registry_snapshot_expired'
        if account not in self.enabled:return 'account_disabled'
        if any(member not in self.enabled for member in view.required.get(account,(account,))):return 'member_disabled'
        return None
    def allowed(self,account,view):
        return self.denial(account,view)is None
    def close_session(self,session):
        account=session.identity['id']
        if self.app.realtime.view.bindings.get(account)==session.shop_session_id:self.closed[account]=session.shop_session_id
    def binding(self,account):return self.app.realtime.view.bindings.get(account)
    def relay_open(self,account):self.lost_relays.pop(account,None)
    def relay_closed(self,account,binding):
        if binding is not None:self.lost_relays[account]=binding
    def target_enabled(self,account):
        return self.allowed(account,self.app.realtime.view)
    def manifest(self,account):
        view=self.app.realtime.view
        reason=self.denial(account,view)
        # Never forward with stale authorization. Await the independent refresh
        # without turning temporary reader/scheduler delay into a lost session.
        if reason=='registry_snapshot_expired':return PENDING
        if reason is not None:raise ValueError('Realtime account authorization unavailable: '+reason)
        return LEGACY if account in view.legacy else view.manifests.get(account,EMPTY)
    def route(self,account,epoch,target):
        view=self.app.realtime.view
        if not self.allowed(account,view):return None
        if account in view.legacy:return LEGACY
        route=view.routes.get((account,epoch,target))
        if route is None or route[0]not in self.enabled:return None
        return route
    def clock(self,session):
        view=self.app.realtime.view;row=view.clocks.get(session.shop_session_id)
        return row[1]if row is not None and self.allowed(row[0],view)else None
    def auxiliary(self,session,event):
        from els_server.domain.session_auxiliary import auxiliary_envelope
        if not auxiliary_envelope(event):return False
        view=self.app.realtime.view;account=view.auxiliary.get(session.shop_session_id)
        return account is not None and self.allowed(account,view)
    async def close(self):
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.executor.shutdown(wait=True,cancel_futures=True)
