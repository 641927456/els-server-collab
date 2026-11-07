"""Real scheduler and asyncio locks: followup ordering, urgency and retirement."""
import bootstrap as h
import asyncio,hashlib,json,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from els_server.periodic_scheduler import PeriodicScheduler

class Tests(unittest.IsolatedAsyncioTestCase):
 async def fixture(self):
  started=asyncio.Event();release=asyncio.Event();release.set();polls=[];sent=[]
  workers=SimpleNamespace(upkeep_available=None,candidate=lambda *a:False)
  async def batch(sessions):
   polls.append(time.monotonic());started.set();await release.wait()
   for s in sessions:s._periodic_due=time.monotonic()+10
   return[([],None)for _ in sessions]
  app=SimpleNamespace(dungeon_workers=workers,periodic_notify=None,periodic_batch=batch,performance=SimpleNamespace(due=lambda:None))
  scheduler=PeriodicScheduler(app,.05,lambda *a,**k:None)
  session=SimpleNamespace(phase='dungeon_active',periodic_notifications=lambda:None,_periodic_pending=False,_periodic_due=time.monotonic()+10)
  operation=asyncio.Lock()
  async def send(messages):sent.append(messages)
  serve=asyncio.create_task(scheduler.serve(session,operation,send));await asyncio.sleep(0)
  slot=next(iter(scheduler.slots.values()));slot.due=time.monotonic()+10
  async def close():
   release.set();await scheduler.close();serve.cancel();await asyncio.gather(serve,return_exceptions=True)
  self.addAsyncCleanup(close)
  return SimpleNamespace(scheduler=scheduler,session=session,operation=operation,slot=slot,started=started,release=release,polls=polls,sent=sent)
 async def foreground(self,f):
  async with f.scheduler.foreground(f.session,f.operation):f.session._periodic_due=time.monotonic()-1
  return time.monotonic()
 async def test_followup_runs_before_fresh_quiet_poll_and_poll_later_runs(self):
  f=await self.fixture();await self.foreground(f)
  await asyncio.sleep(0)
  async with f.scheduler.foreground(f.session,f.operation):self.assertFalse(f.started.is_set())
  completed=f.slot.foreground_completed
  await asyncio.wait_for(f.started.wait(),1)
  self.assertGreaterEqual(f.polls[0],completed+f.scheduler.interval-.001)
 async def test_unread_notification_keeps_original_immediate_turn(self):
  f=await self.fixture();await self.foreground(f);f.scheduler._notify(f.session)
  await asyncio.wait_for(f.started.wait(),1)
  self.assertLess(f.polls[0],f.slot.foreground_completed+f.scheduler.interval)
 async def test_stale_poll_keeps_original_fairness(self):
  f=await self.fixture();await self.foreground(f);f.slot.last_completed=time.monotonic()-1.1
  f.slot.due=time.monotonic()-1;f.scheduler.wake.set();await asyncio.wait_for(f.started.wait(),1)
  self.assertLess(f.polls[0],f.slot.foreground_completed+f.scheduler.interval)
 async def test_notification_arriving_after_grace_is_armed_is_not_delayed(self):
  f=await self.fixture();await self.foreground(f)
  await asyncio.sleep(0);await asyncio.sleep(0)
  late=asyncio.Event();timer=asyncio.get_running_loop().call_later(.025,late.set)
  try:
   f.scheduler._notify(f.session);await asyncio.wait_for(f.started.wait(),1)
   self.assertFalse(late.is_set(),'Notification waited behind the foreground followup grace')
  finally:timer.cancel()
 async def test_grace_never_extends_past_existing_one_second_bound(self):
  f=await self.fixture();await self.foreground(f);f.slot.last_completed=time.monotonic()-.995
  deadline=f.slot.last_completed+1;f.slot.due=time.monotonic()-1;f.scheduler.wake.set()
  await asyncio.wait_for(f.started.wait(),1)
  self.assertGreaterEqual(f.polls[0],deadline-.001)
  self.assertLess(f.polls[0],f.slot.foreground_completed+f.scheduler.interval)
 async def test_already_reserved_operation_is_not_held_for_grace(self):
  f=await self.fixture();await self.foreground(f)
  f.slot.waiting=asyncio.create_task(f.operation.acquire());await f.slot.waiting
  self.assertTrue(f.operation.locked());f.slot.due=time.monotonic()-1;f.scheduler.wake.set()
  await asyncio.wait_for(f.started.wait(),1)
  self.assertLess(f.polls[0],f.slot.foreground_completed+f.scheduler.interval)
 async def test_running_poll_is_never_preempted_or_retired_early(self):
  f=await self.fixture();f.release.clear();f.slot.due=time.monotonic()-1;f.scheduler.wake.set()
  await asyncio.wait_for(f.started.wait(),1);entered=asyncio.Event()
  async def request():
   async with f.scheduler.foreground(f.session,f.operation):entered.set()
  task=asyncio.create_task(request());await asyncio.sleep(0);self.assertFalse(entered.is_set())
  f.release.set();await asyncio.wait_for(task,1);self.assertTrue(entered.is_set());self.assertEqual(len(f.sent),1)

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 report=dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),runtime=sys.version,GIL_enabled=sys._is_gil_enabled(),source=h.SOURCE_BINDINGS,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),production_access=False)
 (h.HERE/'periodic-followup-tests.json').write_text(json.dumps(report,indent=2),'utf8');sys.exit(not result.wasSuccessful())
