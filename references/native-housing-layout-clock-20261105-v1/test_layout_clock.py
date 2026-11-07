"""A real competing SQLite writer crossing the contract deadline."""
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,time
W=Path(__file__).resolve().parent
B=Path(os.environ['ELS_FULL_SOURCE']).resolve()
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor')]
source=B/'els_server/storage/housing_layouts.py'if '--baseline'in sys.argv else W/'source/els_server/storage/housing_layouts.py'
spec=importlib.util.spec_from_file_location('els_server.storage.housing_layouts',source)
layouts=importlib.util.module_from_spec(spec);sys.modules[spec.name]=layouts;spec.loader.exec_module(layouts)
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items
from els_server.storage import housing_access as access,housing_rooms as rooms
from els_server.protocol.housing_layout_messages import encode,REQUEST
START=1900000000
result=dict(passed=False,baseline='--baseline'in sys.argv,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),cases=[],production_database_access=False)
for expire in(True,False):
 with tempfile.TemporaryDirectory(prefix='owned-layout-clock-',dir=W)as name:
  path=Path(name)/'own.sqlite3';prepare(path);roster=Characters(path,1)
  uid=roster.create('OwnClock',1,'owned-clock-character')['uid']
  account=LocalAccount(LocalState(path,uid),account_id=1);account.enable_characters(characters=roster);account.get_inventory_snapshot()
  uid=account.uid;aid=account.account_id
  with closing(sqlite3.connect(path))as db,db:
   db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
   item=grant_items(db,[dict(template=136034,metadata=0,quantity=1,group=4)],uid)[0]
  access.use(path,uid,aid,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0),'owned-contract',lambda db:None,now=START)
  generation=rooms.enter(path,uid,aid,struct.pack('>Qi3fB',0,26000,0,0,0,1),'owned-enter','own-session',account.get_location()['map'],lambda db:None,now=START)['generation']
  with closing(sqlite3.connect(path))as db:before=list(db.iterdump())
  boundary=START+access.SECONDS;clock=[boundary-2];entered=Event()
  class Waiting(sqlite3.Connection):
   def execute(self,sql,*args,**kwargs):
    if sql=='BEGIN IMMEDIATE':entered.set()
    return super().execute(sql,*args,**kwargs)
  def connect(*args,**kwargs):return sqlite3.connect(*args,**kwargs,factory=Waiting)
  payload=encode(REQUEST,([],[],[],0,0,0))
  with closing(sqlite3.connect(path))as holder:
   holder.execute('BEGIN IMMEDIATE')
   with ThreadPoolExecutor(max_workers=1)as pool,patch.object(layouts,'sqlite3',SimpleNamespace(connect=connect)),patch.object(layouts,'time',SimpleNamespace(time=lambda:clock[0])):
    future=pool.submit(layouts.save,path,uid,aid,payload,'owned-save',generation,'owned-enter',lambda db:None)
    assert entered.wait(3),'Owned competing writer did not reach BEGIN'
    clock[0]=boundary if expire else boundary-1
    holder.commit()
    try:events=future.result(timeout=4);accepted=True
    except ValueError as error:
     assert str(error)=='Furniture current housing access',str(error)
     accepted=False
  with closing(sqlite3.connect(path))as db:
   after=list(db.iterdump())
   saved=db.execute('SELECT revision,updated_at FROM character_housing_layouts_v1').fetchall()if rooms.exists(db,layouts.TABLE)else[]
  if expire and not result['baseline']:assert not accepted and before==after and not saved
  else:
   assert accepted
   assert saved==[(1,boundary-2 if result['baseline']else boundary-1)]
  result['cases'].append(dict(contract_expired_while_waiting=expire,accepted=accepted,SQL_unchanged=before==after,saved=saved))
result['passed']=True;result['owned_temporary_directories_removed']=True
p=W/('layout-clock-'+('baseline'if result['baseline']else'fixed')+'-'+str(time.time_ns())+'.json')
p.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(passed=True,baseline=result['baseline'],cases=result['cases'],evidence=str(p))))
