"""Reproduce a cancelled poll retaining the world gate for a 92ms publication."""
import runtime_fixture as h
import asyncio,json,time,threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from els_server.business_queue import BoundedBusinessQueue
from els_server.economy import WorldGate
from els_server.periodic_work import PeriodicClaim,periodic_chunks
from els_server.periodic_scheduler import PeriodicScheduler

async def main():
 pool=ThreadPoolExecutor(max_workers=1);block=threading.Event();entered=threading.Event();calls=[];members=[]
 def occupy():entered.set();block.wait(5)
 busy=pool.submit(occupy);assert entered.wait(1)
 def publish(*args,**kwargs):calls.append('publish');time.sleep(.092)
 app=SimpleNamespace(world_gate=WorldGate(),business_queue=BoundedBusinessQueue(pool),realtime=SimpleNamespace(publish=publish))
 app._worker_call=lambda fn,*args,**kwargs:fn()
 session=SimpleNamespace(periodic_notifications=lambda:members.append('member')or[])
 claim=PeriodicClaim();operation=asyncio.Lock();await operation.acquire()
 slot=SimpleNamespace(session=session,operation=operation,foreground=False,waiting=None,claim=claim,last_completed=time.monotonic())
 scheduler=PeriodicScheduler(app,.05,lambda *args,**kwargs:None);scheduler.slots[1]=slot
 async def poll():return [r async for r in periodic_chunks(app,[session],claims=[claim])]
 task=asyncio.create_task(poll())
 while app.business_queue.inflight!=1:await asyncio.sleep(0)
 assert app.world_gate.writer and claim.state=='pending'
 started=time.perf_counter()
 try:
  async with scheduler.foreground(session,operation):
   assert claim.cancelled
   block.set()
   async with app.world_gate.exclusive(dungeon=True):
    await app.business_queue.run(lambda:None)
  elapsed=(time.perf_counter()-started)*1000
  assert await task==[[([],None)]] and not members
  out=dict(ok=True,cancelled_member_calls=len(members),cancelled_publications=len(calls),foreground_wait_ms=elapsed,preempted=scheduler.metrics['preempted'],world_gate_released=not app.world_gate.writer)
  if '--candidate'in h.sys.argv:assert not calls,'Cancelled batch still rebuilds routing views'
  else:assert len(calls)==1,'Baseline reproduction changed'
 finally:
  block.set();busy.result(1);app.business_queue.close();pool.shutdown(wait=True)
 dest=h.H/('cancelled-periodic-fixed.json'if'--candidate'in h.sys.argv else'cancelled-periodic-baseline.json');assert not dest.exists();dest.write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
asyncio.run(main())
