"""Owned protocol fixture with stage-one and dungeon-route overlays."""
from pathlib import Path
import json
H=Path(__file__).resolve().parent;ROOT=Path('G:/els')
BASE=Path(json.loads((H/'candidate-manifest.json').read_bytes())['resource_parent'])
source=(ROOT/'analysis/pickup-consumable-gate-20261104-v1/runtime_fixture.py').read_text('utf8')
source=source.replace("BASE=ROOT/'releases/online/native-mixed-player-scene-summons-20261104-v1'",'BASE=Path('+repr(str(BASE))+')')
source=source.replace('import els_server.domain,els_server.storage',"""import els_server,els_server.domain,els_server.storage
first=ROOT/'analysis/pet-pickup-latency-20261104-v1/candidate/els_server'
els_server.__path__.insert(0,str(first));els_server.domain.__path__.insert(0,str(first/'domain'))
els_server.storage.__path__.insert(0,str(first/'storage'))""")
source=source.replace("if '--candidate'in sys.argv:\n", "if '--candidate'in sys.argv:\n els_server.__path__.insert(0,str(H/'candidate/els_server'))\n")
exec(compile(source,str(__file__),'exec'))

if '--assert-routes' in sys.argv:
 from contextvars import ContextVar
 from functools import wraps
 import atexit
 from contextlib import asynccontextmanager
 from els_server.application import Application
 from els_server.economy import WorldGate
 from els_server.domain.dungeon_requests import accepts
 active_request=ContextVar('owned_dungeon_route_assertion',default=None)
 seen=set();unexpected=[];original_worker=Application._worker_call
 admission_counts=dict(dungeon=0,ordinary=0);original_exclusive=WorldGate.exclusive
 @asynccontextmanager
 async def exclusive(self,*,dungeon=False):
  admission_counts['dungeon'if dungeon else'ordinary']+=1
  async with original_exclusive(self,dungeon=dungeon):yield
 WorldGate.exclusive=exclusive
 def worker(self,function,args,kwargs,*rest,**options):
  actor=getattr(function,'__self__',None)
  selected=(isinstance(actor,LocalSession)and function.__name__=='handle'and len(args)==1 and accepts(actor,args[0]))
  kind=args[0].kind if selected else None
  token=active_request.set(kind)
  if kind is not None:seen.add(kind)
  try:return original_worker(self,function,args,kwargs,*rest,**options)
  finally:active_request.reset(token)
 from els_server.domain.local_session import LocalSession
 Application._worker_call=worker
 def forbid(module,name):
  original=getattr(module,name)
  @wraps(original)
  def checked(*args,**kwargs):
   kind=active_request.get()
   if kind is not None:
    unexpected.append((hex(kind),module.__name__,name))
    raise AssertionError('Dungeon request reached unrelated route: '+module.__name__+'.'+name)
   return original(*args,**kwargs)
  setattr(module,name,checked)
 import importlib
 for name,function in (('session_dispatch','priority_handlers'),('session_dispatch','feature_handlers'),
                       ('anvil_flow','synchronize'),('housing_access_flow','synchronize'),
                       ('ariel_attendance_preview','project'),('black_market_flow','synchronize'),
                       ('quick_start_flow','synchronize')):
  forbid(importlib.import_module('els_server.domain.'+name),function)
 def receipt():
  name=Path(sys.argv[0]).stem.removeprefix('verify_')
  (H/('route-assertions-'+name+'.json')).write_text(json.dumps(dict(ok=not unexpected and admission_counts['dungeon']>0,handled_kinds=[hex(k)for k in sorted(seen)],admissions=admission_counts,unexpected=unexpected),indent=2),encoding='utf8')
 atexit.register(receipt)
