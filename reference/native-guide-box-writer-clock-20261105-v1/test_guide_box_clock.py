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
source=(W/('baseline'if baseline else'source'))/'els_server/storage/growth_guide_boxes.py'
spec=importlib.util.spec_from_file_location('els_server.storage.growth_guide_boxes',source)
boxes=importlib.util.module_from_spec(spec);sys.modules[spec.name]=boxes;spec.loader.exec_module(boxes)
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.item_expiration import assign
DEADLINE=1900000000;TEMPLATE=722235
report=dict(passed=False,baseline=baseline,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    source_template=TEMPLATE,production_database_access=False,new_timed_source=False,cases=[])
try:
 for expired in((False,)if'--valid-only'in sys.argv else(True,False)):
  with tempfile.TemporaryDirectory(prefix='owned-guide-box-clock-',dir=W)as name:
   path=Path(name)/'own.sqlite3';prepare(path);roster=Characters(path,1)
   uid=roster.create('OwnGuideClk',1,'owned-guide-box-clock')['uid']
   account=LocalAccount(LocalState(path,uid),account_id=1);account.enable_characters(characters=roster);account.get_inventory_snapshot()
   expected={r['template']:r for r in boxes.boxes()[TEMPLATE]['outputs']};assert all(r['period_days']==30 for r in expected.values())
   with closing(sqlite3.connect(path))as db,db:
    item=grant_items(db,[dict(template=TEMPLATE,metadata=VERIFIED_TEMPLATES[TEMPLATE],group=TEMPLATE_BAG_GROUPS[TEMPLATE],quantity=1)],uid)[0]
    assign(db,uid,item['uid'],DEADLINE)
   with closing(sqlite3.connect(path))as db:before=list(db.iterdump());before_uids={i['uid']for i in load_items(db,uid)}
   entered=Event();clock=[DEADLINE-2]
   class Waiting(sqlite3.Connection):
    def execute(self,sql,*args,**kwargs):
     if sql=='BEGIN IMMEDIATE':entered.set()
     return super().execute(sql,*args,**kwargs)
   def connect(*args,**kwargs):return sqlite3.connect(*args,**kwargs,factory=Waiting)
   payload=struct.pack('>QBBBIi',item['uid'],0,0,0,0,0)
   with closing(sqlite3.connect(path))as holder:
    holder.execute('BEGIN IMMEDIATE')
    with ThreadPoolExecutor(max_workers=1)as pool,patch.object(boxes,'sqlite3',SimpleNamespace(connect=connect)),patch.object(boxes,'time',SimpleNamespace(time=lambda:clock[0])):
     future=pool.submit(boxes.open_box,path,uid,TEMPLATE,payload,'owned-guide-box-clock-use');assert entered.wait(3)
     clock[0]=DEADLINE+1 if expired else DEADLINE;holder.commit()
     try:events=future.result(timeout=4);accepted=True;error=None
     except ValueError as e:accepted=False;error=str(e)
   with closing(sqlite3.connect(path))as db:
    after=list(db.iterdump());grants=[i for i in load_items(db,uid)if i['uid']not in before_uids]
   if expired and not baseline:
    assert not accepted and error=='Item has expired'and before==after and not grants
   else:
    assert accepted,str(error);stamp=DEADLINE-2 if baseline else DEADLINE
    assert{g['template']for g in grants}==set(expected)
    assert all(g['expires_at']==stamp+30*86400 for g in grants)
    again=boxes.open_box(path,uid,TEMPLATE,payload,'owned-guide-box-clock-use',now=DEADLINE)
    assert again
    for event in again:boxes.encode_event(event)
    with closing(sqlite3.connect(path))as db:
     assert{g['uid']for g in load_items(db,uid)if g['uid']not in before_uids}=={g['uid']for g in grants}
     assert db.execute('SELECT count(*) FROM inventory_action_receipts WHERE operation_id=?',('owned-guide-box-clock-use',)).fetchone()==(1,)
   report['cases'].append(dict(expired_during_wait=expired,accepted=accepted,error=error,
       granted=[dict(uid=g['uid'],template=g['template'],expires_at=g['expires_at'])for g in grants],SQL_unchanged=before==after))
 report.update(passed=True,owned_temporary_directories_removed=True)
except BaseException:report['error']=traceback.format_exc()
p=W/('guide-box-clock-'+('baseline'if baseline else'fixed')+'-'+str(time.time_ns())+'.json')
p.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(dict(report,evidence=str(p))))
raise SystemExit(not report['passed'])
