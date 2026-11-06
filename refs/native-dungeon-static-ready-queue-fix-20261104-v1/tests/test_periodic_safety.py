import runtime_fixture as h
import asyncio,json,threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from els_server.business_queue import BoundedBusinessQueue
from els_server.economy import WorldGate
from els_server.periodic_work import PeriodicClaim,periodic_chunks

async def main():
 pool=ThreadPoolExecutor(max_workers=1);publications=[];ran=[]
 app=SimpleNamespace(world_gate=WorldGate(),business_queue=BoundedBusinessQueue(pool),realtime=SimpleNamespace(publish=lambda *a,**k:publications.append(tuple(ran))))
 app._worker_call=lambda fn,*a,**k:fn()
 def session(fn):return SimpleNamespace(periodic_notifications=fn)
 def work(value):ran.append(value);return [value]
 async def collect(members,claims):return [r async for r in periodic_chunks(app,members,claims=claims)]
 try:
  skipped=PeriodicClaim();assert skipped.cancel();active=PeriodicClaim()
  result=await collect([session(lambda:work('cancelled')),session(lambda:work('committed'))],[skipped,active])
  assert result==[[([],None),(['committed'],None)]]and ran==['committed']and len(publications)==1
  entered=threading.Event();release=threading.Event();claim=PeriodicClaim()
  def atomic():entered.set();assert release.wait(2);return work('atomic-completed')
  task=asyncio.create_task(collect([session(atomic)],[claim]))
  while not entered.is_set():await asyncio.sleep(0)
  assert not claim.cancel()and claim.state=='running';release.set()
  assert await task==[[(['atomic-completed'],None)]]and len(publications)==2
  def failure():raise ValueError('owned member failure')
  result=await collect([session(failure)],[PeriodicClaim()])
  assert len(result)==1 and isinstance(result[0][0][1],ValueError)and len(publications)==3
  assert not app.world_gate.writer
 finally:app.business_queue.close();pool.shutdown(wait=True)
 out=dict(ok=True,mixed_batch_preserves_order=True,started_member_cannot_be_cancelled=True,started_failure_publishes_and_releases_gate=True,publications=len(publications))
 p=h.H/'periodic-safety.json';assert not p.exists();p.write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
asyncio.run(main())
