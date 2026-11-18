from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,time
W=Path(__file__).resolve().parent;B=Path(os.environ['ELS_FULL_SOURCE']).resolve()
baseline='--baseline'in sys.argv;sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor')]
import els_server,els_server.storage,els_server.domain
source=(B if baseline else W/'source')/'els_server/storage/titles.py'
spec=importlib.util.spec_from_file_location('els_server.storage.titles',source)
titles=importlib.util.module_from_spec(spec);sys.modules[spec.name]=titles;spec.loader.exec_module(titles)
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.item_expiration import assign
DEADLINE=1900000000
report=dict(passed=False,baseline=baseline,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            source_template=81650,production_database_access=False,cases=[])
for expired in(True,False):
 with tempfile.TemporaryDirectory(prefix='owned-title-clock-',dir=W)as name:
  path=Path(name)/'own.sqlite3';prepare(path);roster=Characters(path,1)
  uid=roster.create('OwnTitleClk',1,'owned-title-clock')['uid']
  account=LocalAccount(LocalState(path,uid),account_id=1);account.enable_characters(characters=roster);account.get_inventory_snapshot()
  rule=titles.catalog()['items']['81650'];assert rule['title']==10970
  with closing(sqlite3.connect(path))as db,db:
   db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
   item=grant_items(db,[dict(template=81650,metadata=rule['metadata'],group=rule['group'],quantity=1)],uid)[0]
   assign(db,uid,item['uid'],DEADLINE)
  with closing(sqlite3.connect(path))as db:before=list(db.iterdump())
  entered=Event();clock=[DEADLINE-2]
  class Waiting(sqlite3.Connection):
   def execute(self,sql,*args,**kwargs):
    if sql=='BEGIN IMMEDIATE':entered.set()
    return super().execute(sql,*args,**kwargs)
  def connect(*args,**kwargs):return sqlite3.connect(*args,**kwargs,factory=Waiting)
  payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
  with closing(sqlite3.connect(path))as holder:
   holder.execute('BEGIN IMMEDIATE')
   with ThreadPoolExecutor(max_workers=1)as pool,patch.object(titles,'sqlite3',SimpleNamespace(connect=connect)),patch.object(titles,'time',SimpleNamespace(time=lambda:clock[0])):
    future=pool.submit(titles.use_item,path,uid,payload,'owned-title-clock-use');assert entered.wait(3)
    clock[0]=DEADLINE+1 if expired else DEADLINE;holder.commit()
    try:result=future.result(timeout=4);accepted=True;error=None
    except ValueError as e:accepted=False;error=str(e)
  with closing(sqlite3.connect(path))as db:
   after=list(db.iterdump())
   owned=db.execute('SELECT title,acquired_at FROM title_ownership').fetchall()if titles.exists(db,'title_ownership')else[]
   items=load_items(db,uid)
  if expired and not baseline:
   assert not accepted and error=='Item has expired'and before==after and not owned
  else:
   assert accepted,str(error);assert owned==[(10970,DEADLINE-2 if baseline else DEADLINE)]
   assert all(i['uid']!=item['uid']for i in items)
   again=titles.use_item(path,uid,payload,'owned-title-clock-use',now=DEADLINE)
   assert again['replayed']
   with closing(sqlite3.connect(path))as db:assert db.execute('SELECT count(*) FROM title_ownership').fetchone()==(1,)
  report['cases'].append(dict(expired_during_wait=expired,accepted=accepted,error=error,owned=owned,SQL_unchanged=before==after))
report.update(passed=True,owned_temporary_directories_removed=True)
p=W/('title-clock-'+('baseline'if baseline else'fixed')+'-'+str(time.time_ns())+'.json')
p.write_text(json.dumps(report,indent=2),'utf8');print(json.dumps(dict(report,evidence=str(p))))
