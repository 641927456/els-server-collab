"""Due-time fairness while real asynchronous work exceeds the poll interval."""
import asyncio,time,unittest
from types import SimpleNamespace
from els_server.periodic_scheduler import PeriodicScheduler

class DeadlineFairnessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.batches=[];self.gate=asyncio.Event();self.tasks=[]
        async def batch(members):
            self.batches.append(tuple(members))
            await asyncio.sleep(.04)
            if len(self.batches)>=4:self.gate.set()
            return [([],None)for _ in members]
        app=SimpleNamespace(periodic_batch=batch,performance=SimpleNamespace(due=lambda:None),preparation=SimpleNamespace(snapshot=lambda:{}))
        self.scheduler=PeriodicScheduler(app,.02,lambda *a,**kw:None)
    async def asyncTearDown(self):
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.scheduler.close()
    async def enroll(self,oldest_last=False):
        async def send(messages):pass
        locks=[asyncio.Lock()for _ in range(64)]
        for lock in locks:await lock.acquire()
        self.tasks=[asyncio.create_task(self.scheduler.serve(i,locks[i],send))for i in range(64)]
        async with asyncio.timeout(2):
            while len(self.scheduler.slots)<64:await asyncio.sleep(0)
        due=time.monotonic()-10
        for slot in self.scheduler.slots.values():
            slot.due=due-1 if oldest_last and slot.session>=48 else due
        for lock in locks:lock.release()
        self.scheduler.wake.set()
    async def test_slow_worker_cannot_recycle_first_cohorts_before_all_due_peers(self):
        await self.enroll()
        await asyncio.wait_for(self.gate.wait(),3)
        self.assertEqual(len(self.batches[:4]),4)
        self.assertTrue(all(len(b)==16 for b in self.batches[:4]))
        self.assertEqual(set().union(*map(set,self.batches[:4])),set(range(64)))
        self.assertEqual(self.scheduler.metrics['max_batch'],16)
    async def test_older_deadlines_beat_registration_order(self):
        await self.enroll(oldest_last=True)
        await asyncio.wait_for(self.gate.wait(),3)
        self.assertEqual(set(self.batches[0]),set(range(48,64)))
        self.assertEqual(set().union(*map(set,self.batches[:4])),set(range(64)))

if __name__=='__main__':unittest.main()
