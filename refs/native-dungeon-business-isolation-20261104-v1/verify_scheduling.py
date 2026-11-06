"""Exercise actual admission ordering and cancellation with the real queue."""
import asyncio,concurrent.futures,importlib.util,json,sys,threading,time
from pathlib import Path
H=Path(__file__).resolve().parent
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
economy=load('isolated_gate',H/'source/els_server/economy.py')
queue_module=load('actual_queue',H/'dependencies/els_server/business_queue.py')
async def main():
 checks=[];gate=economy.WorldGate();order=[]
 async def request(name,dungeon=False):
  async with gate.exclusive(dungeon=dungeon):
   assert gate.readers==0;order.append(name);await asyncio.sleep(0)
 async with gate.exclusive():
  jobs=[asyncio.create_task(request('town'+str(i)))for i in range(30)]
  await asyncio.sleep(0)
  jobs.extend(asyncio.create_task(request('dungeon'+str(i),True))for i in range(18))
  await asyncio.sleep(0)
 await asyncio.gather(*jobs)
 assert order[:16]==['dungeon'+str(i)for i in range(16)] and order[16]=='town0'
 assert order[17:19]==['dungeon16','dungeon17']
 assert [s for s in order if s.startswith('town')]==['town'+str(i)for i in range(30)]
 checks.append('dungeon FIFO bypasses thirty queued town writers; ordinary writer admitted after sixteen dungeon requests')
 async with gate.parallel():
  jobs=[asyncio.create_task(request('cancelled',True)),asyncio.create_task(request('survivor'))]
  await asyncio.sleep(0);jobs[0].cancel()
  try:await jobs[0]
  except asyncio.CancelledError:pass
  assert not jobs[1].done()
 await jobs[1];assert order[-1]=='survivor' and not gate.waiting_writer
 checks.append('reader barrier retained; cancelling waiting dungeon request releases its admission exactly once')
 started=threading.Event();release=threading.Event();finished=threading.Event()
 executor=concurrent.futures.ThreadPoolExecutor(max_workers=1)
 queue=queue_module.BoundedBusinessQueue(executor)
 def transaction():started.set();assert release.wait(3);finished.set()
 async def active():
  async with gate.exclusive(dungeon=True):await queue.run(transaction)
 task=asyncio.create_task(active())
 while not started.is_set():await asyncio.sleep(.001)
 task.cancel();task.cancel();next_task=asyncio.create_task(request('after-cancel'))
 await asyncio.sleep(.01);assert not next_task.done() and gate.writer and not finished.is_set()
 release.set()
 try:await task
 except asyncio.CancelledError:pass
 await next_task;assert finished.is_set() and not gate.writer
 queue.close();executor.shutdown(wait=True,cancel_futures=True)
 checks.append('cancelled running SQL retains exclusive world ownership until actual worker retirement')
 async def parallel():
  async with gate.parallel():assert not gate.writer;await asyncio.sleep(.001)
 await asyncio.gather(*(parallel()if i%3==0 else request(str(i),i%2==0)for i in range(100)))
 assert gate.readers==0 and not gate.writer and not gate.waiting_writer
 checks.append('mixed one hundred reader/dungeon/ordinary admissions retire without overlapping world writers')
 out=dict(ok=True,checks=checks)
 print(json.dumps(out))
asyncio.run(main())
