"""Source-extracted metadata classification and queued-window lifetime checks."""
import ast,asyncio,importlib.util,os,struct,types,unittest
from pathlib import Path
H=Path(__file__).resolve().parent;S=H/'source/els_server'
spec=importlib.util.spec_from_file_location('prior_queued_peer_cases',H/'support/test_queued_peer_window.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior);prior.SOURCE=S/'application.py'
class QueuedMetadata(prior.Tests):
 async def asyncSetUp(self):
  await super().asyncSetUp();self.app.dungeon_workers.town_peer_delivery=lambda fn,args:args in((555,),(1165,))
 async def test_metadata_queued_window_and_cancellation(self):
  await self.lock.acquire();task=asyncio.create_task(self.call(1165));await asyncio.sleep(0)
  self.assertTrue(self.actor._peer_drain_open);self.assertFalse(self.started.is_set());task.cancel()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertFalse(self.actor._peer_drain_open);self.lock.release()
class MetadataModels(unittest.TestCase):
 def test_peer_window_only_adds_qualified_metadata_to_original_moves(self):
  t=ast.parse((S/'dungeon_workers.py').read_bytes());c=next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name=='DungeonWorkers')
  wanted=[n for n in c.body if isinstance(n,ast.FunctionDef)and n.name in('town_metadata','town_peer_delivery')]
  cls=type('OwnWorkers',(),{});eligible=[True]
  cls.town_movement=staticmethod(lambda fn,args:eligible[0]);cls.ordinary_town_move=staticmethod(lambda fn,args:bool(args)and args[0].kind==0x22b)
  ns=dict(DungeonWorkers=cls);exec(compile(ast.Module(body=wanted,type_ignores=[]),str(S/'dungeon_workers.py'),'exec'),ns)
  cls.town_metadata=staticmethod(ns['town_metadata'].__func__);fn=ns['town_peer_delivery'].__func__
  for kind,expected in [(0x48d,True),(0x22b,True),(0x225,False),(0x219,False),(0x67,False)]:self.assertEqual(fn(None,(types.SimpleNamespace(kind=kind),)),expected)
  eligible[0]=False;self.assertFalse(fn(None,(types.SimpleNamespace(kind=0x48d),)))
 def test_original_role_guard_and_account_only_metadata_payload(self):
  t=ast.parse((S/'domain/local_session.py').read_bytes());c=next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name=='LocalSession');method=next(n for n in c.body if isinstance(n,ast.FunctionDef)and n.name=='_handle')
  branch=next(n for n in method.body if isinstance(n,ast.If)and ast.unparse(n.test)=='kind == 1165')
  calls=[]
  def response(kind,build,*,account_id):calls.append((kind,build,account_id));return struct.pack('>Qi',account_id,0)
  ns=dict(responses=response,SessionOrderError=ValueError);body=ast.parse('kind=event.kind').body+[branch]
  wrapper=ast.parse('def own(self,event):\n pass').body[0];wrapper.body=body;exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'original-metadata-branch','exec'),ns)
  for account in(1,2**63-1):
   actor=types.SimpleNamespace(role='game',phase='town_ready',client_build='dx11_260923',account=types.SimpleNamespace(account_id=account))
   self.assertEqual(ns['own'](actor,types.SimpleNamespace(kind=0x48d)),struct.pack('>Qi',account,0))
  for role,phase in [('frontend','town_ready'),('game','new'),('game','game_connected')]:
   with self.assertRaises(ValueError):ns['own'](types.SimpleNamespace(role=role,phase=phase),types.SimpleNamespace(kind=0x48d))
  self.assertEqual(len(calls),2)
if __name__=='__main__':unittest.main()
