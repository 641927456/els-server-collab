import asyncio,types,unittest,sys,importlib.util
from pathlib import Path
A=Path(__file__).resolve().parents[1];sys.path.insert(0,str(A/'runtime-parent'))
spec=importlib.util.spec_from_file_location('tested_native_scheduler',A/'source/els_server/periodic_scheduler.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from collections import deque
class NoticeWakeTests(unittest.IsolatedAsyncioTestCase):
 async def check(self,role,phase,immediate,during_delivery=False):
  real_time=module.time;clock=types.SimpleNamespace(value=100.0);module.time=types.SimpleNamespace(monotonic=lambda:clock.value)
  class Workers:
   upkeep_available=None
   def candidate(self,*args):return False
  class Session:
   def periodic_notifications(self):return []
  s=Session();s.role=role;s.phase=phase;s.mailbox=types.SimpleNamespace(messages=deque())
  class App:
   dungeon_workers=Workers();periodic_notify=None;performance=types.SimpleNamespace(due=lambda:None)
   async def periodic_batch(self,sessions):
    result=[]
    for session in sessions:
     messages=list(session.mailbox.messages);session.mailbox.messages.clear();result.append((messages,None))
    return result
  app=App();scheduler=module.PeriodicScheduler(app,.05,lambda *a,**k:None);delivered=asyncio.Event();values=[];first_started=asyncio.Event();release_first=asyncio.Event()
  async def send(messages):
   values.extend(messages)
   if during_delivery and len(values)==1:first_started.set();await release_first.wait()
   if len(values)>=(2 if during_delivery else 1):delivered.set()
  serving=asyncio.create_task(scheduler.serve(s,asyncio.Lock(),send))
  try:
   await asyncio.sleep(0);await asyncio.sleep(0)
   notice=object();s.mailbox.messages.append(notice);scheduler.notify(s)
   if not immediate:
    for _ in range(12):await asyncio.sleep(0)
    self.assertFalse(delivered.is_set());clock.value+=.05;scheduler.wake.set()
   expected=[notice]
   if during_delivery:
    async with asyncio.timeout(.5):await first_started.wait()
    second=object();s.mailbox.messages.append(second);scheduler.notify(s);expected.append(second)
    for _ in range(4):await asyncio.sleep(0)
    release_first.set()
   async with asyncio.timeout(.5):await delivered.wait()
   self.assertEqual(values,expected);await asyncio.sleep(0)
   self.assertEqual(scheduler.metrics['completed_polls'],len(expected))
   await asyncio.sleep(.06);self.assertEqual(scheduler.metrics['completed_polls'],len(expected))
   self.assertFalse(serving.done(),repr(serving.exception())if serving.done()and not serving.cancelled()else None)
  finally:
   serving.cancel();await asyncio.gather(serving,return_exceptions=True)
   await scheduler.close();module.time=real_time
 async def test_pending_game_town_notice_uses_current_turn(self):await self.check('game','town_ready',True)
 async def test_new_notice_during_delivery_keeps_immediate_followup(self):await self.check('game','town_ready',True,True)
 async def test_frontend_keeps_existing_poll_interval(self):await self.check('frontend','authenticated',False)
if __name__=='__main__':unittest.main(argv=[__file__])
