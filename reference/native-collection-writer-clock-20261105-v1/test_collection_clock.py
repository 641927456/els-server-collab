from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;B=Path(os.environ['ELS_FULL_SOURCE']).resolve()
baseline='--baseline'in sys.argv;sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor')]
import els_server,els_server.storage,els_server.domain
source=(W/('baseline'if baseline else'source'))/'els_server/storage/el_search_collection_tickets.py'
spec=importlib.util.spec_from_file_location('els_server.storage.el_search_collection_tickets',source)
tickets=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tickets;spec.loader.exec_module(tickets)
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.item_expiration import assign
from els_server.storage import el_search_collection as collection,ep_points
from els_server.domain.el_search_collection import classes
from els_server.storage.seal_quests import load_character
DEADLINE=1900000000
report=dict(passed=False,baseline=baseline,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    source_template=980044,production_database_access=False,new_timed_source=False,cases=[])
try:
 for expired in(True,False):
  with tempfile.TemporaryDirectory(prefix='owned-collection-clock-',dir=W)as name:
   path=Path(name)/'own.sqlite3';prepare(path);roster=Characters(path,1)
   uid=roster.create('OwnCollClk',1,'owned-collection-clock')['uid']
   account=LocalAccount(LocalState(path,uid),account_id=1);account.enable_characters(characters=roster);account.get_inventory_snapshot()
   with closing(sqlite3.connect(path))as db,db:
    cls=next(k for k,v in classes().items()if v['unit_type']==1 and v['job_stage']==1)
    db.execute('UPDATE characters SET level=99,unit_class=? WHERE uid=?',(cls,uid))
    ep_points.credit(db,uid,500);collection.activate(db,uid,1,load_character(db,uid),DEADLINE-100)
    item=grant_items(db,[dict(template=980044,metadata=0,group=4,quantity=1)],uid)[0]
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
    with ThreadPoolExecutor(max_workers=1)as pool,patch.object(tickets,'sqlite3',SimpleNamespace(connect=connect)),patch.object(tickets,'time',SimpleNamespace(time=lambda:clock[0])):
     future=pool.submit(tickets.use,path,uid,1,payload,'owned-collection-clock-use',lambda db:None);assert entered.wait(3)
     clock[0]=DEADLINE+1 if expired else DEADLINE;holder.commit()
     try:events=future.result(timeout=4);accepted=True;error=None
     except ValueError as e:accepted=False;error=str(e)
   with closing(sqlite3.connect(path))as db:
    after=list(db.iterdump());state=collection.snapshot(db,uid,1)
    timer=db.execute('SELECT expires_at,updated_at FROM character_search_collection_synergy_time').fetchone()if collection.exists(db,tickets.TABLE)else None
   if expired and not baseline:
    assert not accepted and error=='Item has expired'and before==after and state['expiry']==0
   else:
    assert accepted,str(error)
    expected=DEADLINE-2 if baseline else DEADLINE
    assert timer==(expected+tickets.catalog()[980044],expected)
    with closing(sqlite3.connect(path))as db:assert not any(i['uid']==item['uid']for i in load_items(db,uid))
    again=tickets.use(path,uid,1,payload,'owned-collection-clock-use',lambda db:None,now=DEADLINE)
    assert [e.kind for e in again]==[e.kind for e in events]
    with closing(sqlite3.connect(path))as db:assert db.execute('SELECT count(*) FROM inventory_action_receipts WHERE operation_id=?',('owned-collection-clock-use',)).fetchone()==(1,)
   report['cases'].append(dict(expired_during_wait=expired,accepted=accepted,error=error,timer=timer,SQL_unchanged=before==after))
 report.update(passed=True,owned_temporary_directories_removed=True)
except BaseException:report['error']=traceback.format_exc()
p=W/('collection-clock-'+('baseline'if baseline else'fixed')+'-'+str(time.time_ns())+'.json')
p.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(dict(report,evidence=str(p))))
raise SystemExit(not report['passed'])
