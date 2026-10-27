import asyncio
from contextlib import closing
from pathlib import Path
import tempfile
import secrets
import threading
import time
from types import SimpleNamespace
import unittest

from els_server.application import Application
from els_server.config import ServerConfig
from els_server.periodic_scheduler import PeriodicScheduler
from els_server.preparation import BoundedPreparation,PreparationBusy
from els_server.performance import OperationMetrics
from els_server.accounts_gateway import AccountGateway
from els_server.storage.accounts import Accounts


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app=SimpleNamespace(performance=OperationMetrics(),preparation=SimpleNamespace(snapshot=lambda:{}))
        self.batches=[];self.calls={};self.sent={}
        async def batch(sessions):
            self.batches.append(tuple(sessions))
            for s in sessions:self.calls[s]=self.calls.get(s,0)+1
            return [([s],None) for s in sessions]
        self.app.periodic_batch=batch
        self.scheduler=PeriodicScheduler(self.app,.02,lambda *a,**k:None)
        self.tasks=[]

    def peer(self,key,lock=None,send=None):
        lock=lock or asyncio.Lock()
        async def deliver(messages):self.sent.setdefault(key,[]).append(messages)
        task=asyncio.create_task(self.scheduler.serve(key,lock,send or deliver));self.tasks.append(task)
        return task,lock

    async def asyncTearDown(self):
        for t in self.tasks:t.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.scheduler.close()

    async def wait_for(self,condition):
        async with asyncio.timeout(2):
            while not condition():await asyncio.sleep(.002)

    async def test_sixty_four_peers_are_bounded_fair_and_submit_four_batches(self):
        for i in range(64):self.peer(i)
        await self.wait_for(lambda:len(self.sent)==64)
        self.assertTrue(all(0<len(b)<=16 for b in self.batches))
        self.assertEqual(set().union(*(set(b) for b in self.batches[:4])),set(range(64)))
        self.assertEqual(self.scheduler.metrics['max_batch'],16)
        self.assertLess(len(self.batches),64)

    async def test_operation_lock_preserves_request_reply_boundary(self):
        lock=asyncio.Lock();await lock.acquire();self.peer('busy',lock);self.peer('free')
        await self.wait_for(lambda:'free' in self.sent)
        self.assertNotIn('busy',self.calls)
        lock.release();await self.wait_for(lambda:'busy' in self.sent)

    async def test_slow_sender_does_not_block_other_connections_or_repeat_work(self):
        gate=asyncio.Event();entered=asyncio.Event()
        async def slow(messages):entered.set();await gate.wait()
        _,lock=self.peer('slow',send=slow);self.peer('free')
        await asyncio.wait_for(entered.wait(),2)
        await self.wait_for(lambda:self.calls.get('free',0)>=3)
        self.assertEqual(self.calls['slow'],1);self.assertTrue(lock.locked())
        gate.set()

    async def test_disconnect_during_worker_waits_for_work_before_unlocking(self):
        entered=asyncio.Event();gate=asyncio.Event()
        async def batch(sessions):entered.set();await gate.wait();return [([],None)]
        self.app.periodic_batch=batch
        task,lock=self.peer('actor');await entered.wait();task.cancel()
        await asyncio.sleep(.005);self.assertTrue(lock.locked());self.assertFalse(task.done())
        gate.set();await asyncio.gather(task,return_exceptions=True)
        self.assertFalse(lock.locked());self.assertNotIn('actor',self.sent)

    async def test_failed_member_closes_only_itself(self):
        async def batch(sessions):return [(None,ValueError('disabled')) if s=='bad' else ([s],None) for s in sessions]
        self.app.periodic_batch=batch
        bad,_=self.peer('bad');good,_=self.peer('good')
        await self.wait_for(bad.done)
        self.assertIsInstance(bad.exception(),ValueError)
        await self.wait_for(lambda:'good' in self.sent);self.assertFalse(good.done())


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_call_retains_capacity_and_never_queues_third(self):
        pool=BoundedPreparation();gate=threading.Event();entered=threading.Event()
        def work():entered.set();gate.wait(3);return 7
        tasks=[asyncio.create_task(pool.run(work)) for _ in range(2)]
        try:
            await asyncio.to_thread(entered.wait,1);await asyncio.sleep(.01)
            tasks[0].cancel();await asyncio.gather(tasks[0],return_exceptions=True)
            with self.assertRaises(PreparationBusy):await pool.run(lambda:99)
            self.assertEqual(pool.snapshot()['active'],2)
            gate.set();self.assertEqual(await tasks[1],7)
            for _ in range(50):
                if pool.snapshot()['active']==0:break
                await asyncio.sleep(.002)
            self.assertEqual(await pool.run(lambda:9),9)
        finally:gate.set();pool.close()


class WorkerBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_member_has_separate_scope_clock_and_shared_room_poll(self):
        from unittest.mock import Mock,patch
        from els_server.application import FriendsSession
        from els_server.domain.local_session import LocalSession
        from els_server.domain.friends_world import Mailbox
        from els_server.storage.read_scope import _current
        app=Application(ServerConfig(profile='bootstrap'));self.addCleanup(app.close)
        room=object();poll=Mock();scopes=[];observed=[]
        app.registry=SimpleNamespace(enabled=lambda _:True)
        app.world=SimpleNamespace(party_of={},field_bosses=SimpleNamespace(periodic=lambda s:None),
            dungeons=SimpleNamespace(room=lambda s:room,periodic=poll))
        members=[]
        for i in range(2):
            s=FriendsSession.__new__(FriendsSession)
            s.application=app;s.identity={'id':i};s.social_overflow=False;s.coop_error=None
            s.next_periodic=time.monotonic()+60;s.mailbox=Mailbox()
            def observe(s):scopes.append(_current.get());observed.append(s)
            s.activity2026_awards=SimpleNamespace(online=SimpleNamespace(observe=observe))
            members.append(s)
        result=await app.periodic_batch(members)
        self.assertEqual(result,[([],None),([],None)])
        self.assertEqual(poll.call_count,1)
        self.assertEqual(observed,[members[0],members[0],members[1],members[1]])
        self.assertIs(scopes[0],scopes[1]);self.assertIs(scopes[2],scopes[3]);self.assertIsNot(scopes[0],scopes[2])
        self.assertEqual(app.performance.snapshot()['periodic_notifications']['count'],2)
        # Direct calls retain their ordinary room path outside a batch.
        await app.call(members[0].periodic_notifications)
        self.assertEqual(poll.call_count,2)


class CredentialTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]);self.addCleanup(self.temp.cleanup)
        self.app=Application(ServerConfig(profile='bootstrap'))
        self.registry=Accounts(Path(self.temp.name)/'accounts.sqlite3');self.app.registry=self.registry
        config=SimpleNamespace(registration_enabled=True,max_registered_accounts=64)
        self.gateway=AccountGateway(config,self.app);self.addCleanup(self.app.close)
        self.password=secrets.token_urlsafe(24)

    async def request(self,op,name='qa_actor',password=None,host='127.0.0.1'):
        return await self.gateway.request(dict(op=op,name=name,password=password or self.password),host)

    async def test_registration_login_resume_wrong_password_and_session_cap(self):
        created=await self.request('register');self.assertTrue(created['ok'])
        for _ in range(10):self.assertTrue((await self.request('login'))['ok'])
        with closing(self.registry.connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM account_sessions').fetchone()[0],8)
        failed=await self.request('login',password=secrets.token_urlsafe(24));self.assertEqual(failed['error'],'bad_credentials')
        resumed=await self.gateway.request(dict(op='resume',name=created['name'],token=created['token']),'different-host')
        self.assertFalse(resumed['ok']) # oldest credential was pruned by the existing cap
        self.assertEqual((await self.request('register'))['error'],'name_taken')

    async def test_slow_hash_does_not_block_writer_and_external_disable_rejects(self):
        self.assertTrue((await self.request('register'))['ok'])
        original=self.registry.password_digest;gate=threading.Event();entered=threading.Event()
        def slow(raw,salt):entered.set();gate.wait(3);return original(raw,salt)
        self.registry.password_digest=slow
        task=asyncio.create_task(self.request('login'))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,1))
            self.assertEqual(await asyncio.wait_for(self.app.call(lambda:42),.5),42)
            with closing(self.registry.connect()) as db,db:db.execute('UPDATE accounts SET enabled=0')
            gate.set();self.assertEqual((await task)['error'],'bad_credentials')
            with closing(self.registry.connect()) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM account_sessions').fetchone()[0],1)
        finally:gate.set();await asyncio.gather(task,return_exceptions=True)

    async def test_password_change_between_prepare_and_commit_rejects(self):
        self.assertTrue((await self.request('register'))['ok'])
        proof=await self.app.preparation.run(self.registry.prepare_password_login,'qa_actor',self.password)
        with closing(self.registry.connect()) as db,db:db.execute('UPDATE account_passwords SET digest=?',(bytes(32),))
        with self.assertRaisesRegex(ValueError,'bad_credentials'):await self.app.call(self.registry.finish_password_login,proof)

    async def test_registration_capacity_rechecked_at_commit(self):
        proof=await self.app.preparation.run(self.registry.prepare_registration,'qa_new',self.password)
        await self.app.call(self.registry.create,'qa_filler')
        self.gateway.config.max_registered_accounts=1
        with self.assertRaisesRegex(ValueError,'registration_full'):
            await self.app.call(self.gateway._finish_credentials,self.registry,'register',proof)

    async def test_registry_replacement_and_registration_switch_rechecked(self):
        self.assertTrue((await self.request('register'))['ok'])
        proof=await self.app.preparation.run(self.registry.prepare_password_login,'qa_actor',self.password)
        old=self.registry.path.with_suffix('.old');self.registry.path.rename(old)
        replacement=Accounts(self.registry.path)
        try:
            with self.assertRaisesRegex(ValueError,'bad_credentials'):await self.app.call(self.registry.finish_password_login,proof)
            registration=await self.app.preparation.run(replacement.prepare_registration,'qa_other',self.password)
            self.gateway.config.registration_enabled=False
            reply=await self.app.call(self.gateway._finish_credentials,self.registry,'register',registration)
            self.assertEqual(reply['error'],'registration_closed')
        finally:replacement.close()


if __name__=='__main__':unittest.main()
