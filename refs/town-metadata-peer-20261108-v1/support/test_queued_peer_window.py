"""Original async admission keeps peer delivery open, with exact cleanup."""
import ast,asyncio,time,types,unittest
from pathlib import Path
H=Path(__file__).resolve().parent
SOURCE=H/'candidate/els_server/application.py'
class FriendsSession:
 def __init__(self):self.identity={'id':1};self._peer_drain_open=False
 def handle(self,event):pass
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  tree=ast.parse(SOURCE.read_bytes());node=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Application')
  method=next(n for n in node.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='call');namespace=dict(time=time,FriendsSession=FriendsSession)
  exec(compile(ast.Module(body=[method],type_ignores=[]),str(SOURCE),'exec'),namespace)
  self.lock=asyncio.Lock();self.started=asyncio.Event();self.release=asyncio.Event();self.actor=FriendsSession()
  self.app=types.SimpleNamespace(economy=types.SimpleNamespace(account_lock=lambda account:self.lock),dungeon_workers=types.SimpleNamespace(ordinary_town_move=lambda function,args:args==(555,)))
  async def dispatch(*args):self.started.set();await self.release.wait();return ['original-result']
  self.app._dispatch=dispatch;self.call=lambda event:namespace['call'](self.app,self.actor.handle,event)
 async def test_peer_delivery_window_covers_waiting_account_admission(self):
  await self.lock.acquire();task=asyncio.create_task(self.call(555));await asyncio.sleep(0)
  self.assertTrue(self.actor._peer_drain_open);self.assertFalse(self.started.is_set());self.lock.release()
  await self.started.wait();self.release.set();self.assertEqual(await task,['original-result']);self.assertFalse(self.actor._peer_drain_open)
 async def test_cancelled_waiter_closes_window_without_dispatch(self):
  await self.lock.acquire();task=asyncio.create_task(self.call(555));await asyncio.sleep(0);task.cancel()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertFalse(self.actor._peer_drain_open);self.assertFalse(self.started.is_set());self.assertTrue(self.lock.locked());self.lock.release()
 async def test_original_failure_closes_window_and_releases_account(self):
  async def failed(*args):raise ValueError('Original failure')
  self.app._dispatch=failed
  with self.assertRaisesRegex(ValueError,'Original failure'):await self.call(555)
  self.assertFalse(self.actor._peer_drain_open);self.assertFalse(self.lock.locked())
 async def test_other_requests_preserve_existing_window(self):
  self.actor._peer_drain_open=True;self.release.set();self.assertEqual(await self.call(179),['original-result']);self.assertTrue(self.actor._peer_drain_open)
if __name__=='__main__':unittest.main()
