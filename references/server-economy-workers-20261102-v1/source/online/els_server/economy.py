"""Account-local economic workers, coordinated with the original world worker."""
import asyncio,sqlite3,struct,threading
from contextlib import asynccontextmanager,closing
from weakref import WeakValueDictionary

DECLINED=object()


class WorldGate:
    """At most sixteen parallel admissions, then give queued world work a turn."""
    def __init__(self):
        self.condition=asyncio.Condition();self.writer_order=asyncio.Lock()
        self.readers=0;self.admissions=0;self.writer=False;self.waiting_writer=False

    @asynccontextmanager
    async def parallel(self):
        async with self.condition:
            await self.condition.wait_for(lambda:not self.writer and
                ((self.readers==0 and not self.waiting_writer)or(self.readers>0 and self.admissions<16)))
            if self.readers==0:self.admissions=0
            self.readers+=1;self.admissions+=1
        try:yield
        finally:
            async with self.condition:
                self.readers-=1
                if self.readers==0:self.condition.notify_all()

    @asynccontextmanager
    async def exclusive(self):
        async with self.writer_order:
            async with self.condition:
                self.waiting_writer=True
                try:await self.condition.wait_for(lambda:self.readers==0)
                finally:self.waiting_writer=False;self.condition.notify_all()
                self.writer=True
            try:yield
            finally:
                async with self.condition:self.writer=False;self.condition.notify_all()


class EconomyWorkers:
    def __init__(self,workers):
        from concurrent.futures import ThreadPoolExecutor
        from els_server.business_queue import BoundedBusinessQueue
        self.workers=workers
        self.executor=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='els-economy')
        self.queue=BoundedBusinessQueue(self.executor,capacity=16)
        self.accounts=WeakValueDictionary();self.lock=threading.Lock()
        self.active=0;self.peak=0;self.completed=0;self.failures=0;self.threads=set()

    def account_lock(self,identity):
        return self.accounts.setdefault(identity,asyncio.Lock())

    @staticmethod
    def candidate(function,args):
        from els_server.application import FriendsSession
        from els_server.protocol.protocol_codec import Event
        session=getattr(function,'__self__',None)
        return (type(session)is FriendsSession and getattr(function,'__func__',None)is FriendsSession.handle
            and len(args)==1 and type(args[0])is Event and args[0].event_id==0x202
            and args[0].kind in(0x196,0x80f,0xea,0xec,0x567))

    @staticmethod
    def selected(session,event):
        from els_server.domain.equipment_chip_flow import current_lease
        if (session.client_build!='dx11_260923'or session.role!='game'or session.phase!='town_ready'
            or session.released or session.coop_error or session.social_overflow or not current_lease(session)):
            return False
        if event.kind==0x80f:return session.shop_test
        if event.kind in(0xea,0xec,0x567):return session.item_test
        if not session.item_test or len(event.payload)<8:return False
        # Classification only. Original dispatch still validates the complete
        # payload, selected actor, item, eligibility, debit and immutable receipt.
        uid=struct.unpack_from('>Q',event.payload)[0]
        with closing(sqlite3.connect(session.account.store.path.absolute().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
            row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(session.account.uid,uid)).fetchone()
        from els_server.domain.inventory_items import role_ice_catalog
        return row is not None and str(row[0])in role_ice_catalog()['pools']

    def invoke(self,session,event,work):
        if not self.selected(session,event):return DECLINED
        with self.lock:
            self.active+=1;self.peak=max(self.peak,self.active);self.threads.add(threading.get_ident())
        try:return work()
        except BaseException:
            with self.lock:self.failures+=1
            raise
        finally:
            with self.lock:self.active-=1;self.completed+=1

    def snapshot(self):
        with self.lock:
            result=dict(workers=self.workers,active=self.active,peak_active=self.peak,
                completed=self.completed,failures=self.failures,threads_used=len(self.threads))
        result['queue']=self.queue.snapshot();return result

    def close(self):
        self.queue.close();self.executor.shutdown(wait=True,cancel_futures=True)
