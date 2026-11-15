"""Bounded dungeon execution, serialized by party or solo account, not world jobs."""
import asyncio,threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager,ExitStack
from contextvars import ContextVar
from weakref import WeakValueDictionary
from els_server.business_queue import BoundedBusinessQueue

KINDS=frozenset((0xd0,0xad,0xb8,0xbb,0xb3,0x471))
_current=ContextVar('dungeon_execution_domain',default=None)

class _Domain:
    def __init__(self):self.lock=threading.RLock();self.members=()

class DungeonWorkers:
    def __init__(self,application):
        self.application=application
        self.executor=ThreadPoolExecutor(max_workers=4,thread_name_prefix='els-dungeon')
        self.queue=BoundedBusinessQueue(self.executor,capacity=16)
        self.domains=WeakValueDictionary();self.admissions=WeakValueDictionary()
        self.catalog_lock=threading.RLock();self.metrics_lock=threading.Lock()
        self.active=0;self.peak=0;self.completed=0;self.threads=set();self.periodic_publish_skips=0;self.foreground_publish_skips=0

    def key(self,session):
        party=self.application.world.party_of.get(session)
        return ('party',id(party))if party is not None else('account',session.identity['id'])

    @staticmethod
    def candidate(function,args):
        from els_server.application import FriendsSession
        from els_server.protocol.protocol_codec import Event
        from els_server.domain.dungeon_requests import accepts
        s=getattr(function,'__self__',None)
        if(type(s)is FriendsSession and getattr(function,'__func__',None)is FriendsSession.periodic_notifications and not args):
            return accepts(s,Event(0x202,kind=0xb3))
        return (type(s)is FriendsSession and getattr(function,'__func__',None)is FriendsSession.handle
                and len(args)==1 and type(args[0])is Event and args[0].kind in KINDS and accepts(s,args[0]))

    def isolated(self,session,event):
        current=_current.get()
        return current is not None and current[0]is session and self.candidate(session.handle,(event,))

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
    def scope(self,session,*,recipients=()):
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
                for member in sorted(set(members)|set(recipients),key=lambda s:s.identity['id']):boxes.enter_context(member.mailbox.lock)
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
    def worker_scope(self,function,args):
        session=self.session_for(function,args)
        manager=getattr(self.application,'activity2026_manager',None)
        if manager is not None and getattr(function,'__self__',None)is manager and function.__name__=='update':
            # A real global activity switch flushes every selected timer.
            # Serialize its existing actors before the world lock is acquired.
            with ExitStack()as scopes:
                for member in sorted(self.application.playing.values(),key=lambda s:s.identity['id']):scopes.enter_context(self.scope(member))
                yield
        elif session is None:yield
        else:
            from els_server.domain.guild_publication import targets
            with self.scope(session,recipients=targets(session,function,args)):yield

    async def run(self,session,work,*,timing):
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
            return await self.queue.run(invoke,timing=timing)

    def publish(self,function,args,*,failed=False,periodic=False,independent=False):
        app=self.application;acquired=[];busy=set()
        # Never wait for the world lock while holding the domain catalog:
        # teardown can already own world and re-enter its existing domain.
        if not app.world_lock.acquire(blocking=not independent):return
        # Publish completed domains without reading another room mid-adoption.
        # New domains cannot enter while the snapshot's lock list is captured.
        try:
            unchanged_foreground=(independent and args and self.candidate(function,args)and args[0].kind in(0xd0,0xad))
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
                try:app.realtime.publish(app,function,args,failed=failed,periodic=periodic,exclude=frozenset(busy))
                finally:
                    for lock in reversed(acquired):lock.release()
        finally:app.world_lock.release()

    def snapshot(self):
        with self.metrics_lock:return dict(active=self.active,peak=self.peak,completed=self.completed,threads=len(self.threads),workers=4,periodic_publish_skips=self.periodic_publish_skips,foreground_publish_skips=self.foreground_publish_skips,queue=self.queue.snapshot())

    def close(self):
        self.queue.close();self.executor.shutdown(wait=True,cancel_futures=True)
