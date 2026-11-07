"""FIFO, cancellation and the actual deadline include quota waiting."""
import asyncio,importlib.util,sys,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'source/els_server/egress_budget.py'
spec=importlib.util.spec_from_file_location('tested_egress',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

class BudgetTests(unittest.IsolatedAsyncioTestCase):
 async def test_small_town_frames_get_bytes_instead_of_one_ticket(self):
  b=m.EgressBudget(.008,40);b.tokens=0;seen=[]
  async def wait(name,size,town):await b.wait(size,transient=town);seen.append(name)
  tasks=[asyncio.create_task(wait('reply0',b.chunk_size,False)),asyncio.create_task(wait('reply1',b.chunk_size,False))]
  tasks.extend(asyncio.create_task(wait('town'+str(i),120,True))for i in range(35))
  await asyncio.sleep(0);b.tokens=16384;b.updated=__import__('time').monotonic();b.wake.set()
  await asyncio.gather(*tasks)
  count=min(35,(b.chunk_size+119)//120)
  self.assertEqual(seen,['reply0',*['town'+str(i)for i in range(count)],'reply1',*['town'+str(i)for i in range(count,35)]]);await b.close()
 async def test_reply_and_town_share_byte_quanta(self):
  b=m.EgressBudget(.008,8);b.tokens=0;seen=[]
  async def wait(n,town):await b.wait(b.chunk_size,transient=town);seen.append(n)
  tasks=[asyncio.create_task(wait('town',True))]+[asyncio.create_task(wait('reply'+str(i),False))for i in range(5)]
  await asyncio.sleep(0)
  # Feed each credit explicitly, without depending on wall-clock timer precision.
  for index in range(len(tasks)):
   b.tokens=b.chunk_size;b.updated=__import__('time').monotonic();b.wake.set()
   while len(seen)<index+1:await asyncio.sleep(0)
  await asyncio.gather(*tasks);self.assertEqual(seen,['reply0','town','reply1','reply2','reply3','reply4']);await b.close()
 async def test_fifo_small_waiter_cannot_pass_old_chunk(self):
  b=m.EgressBudget(.008,3);b.tokens=0;seen=[]
  async def wait(n,size):await b.wait(size);seen.append(n)
  a=asyncio.create_task(wait('old',b.chunk_size));await asyncio.sleep(0)
  c=asyncio.create_task(wait('small',1));await asyncio.sleep(0)
  self.assertEqual(seen,[])
  b.tokens=b.chunk_size;b.updated=__import__('time').monotonic();b.wake.set()
  await asyncio.gather(a,c);self.assertEqual(seen,['old','small']);await b.close()
 async def test_cancel_returns_waiter_capacity(self):
  b=m.EgressBudget(.008,1);b.tokens=0
  a=asyncio.create_task(b.wait(b.chunk_size));await asyncio.sleep(0)
  with self.assertRaises(BufferError):await b.wait(1)
  a.cancel();await asyncio.gather(a,return_exceptions=True);self.assertEqual(len(b.waiters),0)
  b.tokens=b.chunk_size;b.updated=__import__('time').monotonic();await b.wait(1);await b.close()
 async def test_whole_deadline_cancels_quota_wait(self):
  b=m.EgressBudget(.008,1);b.tokens=0
  with self.assertRaises(TimeoutError):
   async with asyncio.timeout(.01):await b.wait(b.chunk_size)
  self.assertEqual(len(b.waiters),0);await b.close();self.assertIsNone(b.task)
 async def test_close_releases_waiters(self):
  b=m.EgressBudget(.008,1);b.tokens=0
  a=asyncio.create_task(b.wait(b.chunk_size));await asyncio.sleep(0);await b.close()
  with self.assertRaises(ConnectionError):await a
  self.assertIsNone(b.task)
if __name__=='__main__':unittest.main()
