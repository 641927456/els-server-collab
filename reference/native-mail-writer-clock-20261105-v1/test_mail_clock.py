"""Owned durable mail actions crossing a deadline behind another real writer."""
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,json,os,sqlite3,sys,tempfile,time

W=Path(__file__).resolve().parent
B=Path(os.environ['ELS_FULL_SOURCE']).resolve()
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor')]
import els_server,els_server.storage,els_server.domain
source=B/'els_server/storage/game_mail.py'if '--baseline'in sys.argv else W/'source/els_server/storage/game_mail.py'
spec=importlib.util.spec_from_file_location('els_server.storage.game_mail',source)
mail=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mail;spec.loader.exec_module(mail)
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState

DEADLINE=1900000000
report=dict(passed=False,baseline='--baseline'in sys.argv,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            cases=[],production_database_access=False,actual_SQL_writer_competition=True)
for action,expired in [('claim',True),('claim',False),('read',True),('delete',True)]:
 with tempfile.TemporaryDirectory(prefix='owned-mail-clock-',dir=W)as name:
  path=Path(name)/'own.sqlite3';prepare(path);roster=Characters(path,1)
  uid=roster.create('OwnMailClock',1,'owned-mail-clock-character')['uid']
  account=LocalAccount(LocalState(path,uid),account_id=1);account.enable_characters(characters=roster);account.get_inventory_snapshot()
  with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
  ids=mail.gm_campaign(path,'owned-mail-clock',[1],ed=900,title='Owned clock',body='Own isolation',now=DEADLINE-365*86400)['mails']
  mid=ids[0]['id']
  with closing(sqlite3.connect(path))as db:before=list(db.iterdump())
  clock=[DEADLINE-2];entered=Event();called=[]
  class Waiting(sqlite3.Connection):
   def execute(self,sql,*args,**kwargs):
    if sql=='BEGIN IMMEDIATE':entered.set()
    return super().execute(sql,*args,**kwargs)
  def connect(*args,**kwargs):return sqlite3.connect(*args,**kwargs,factory=Waiting)
  def encode(*args):called.append(args);return args
  method=getattr(mail,action);args=(path,1,uid,mid if action=='read'else[mid],encode)
  fake_sqlite=SimpleNamespace(connect=connect,Row=sqlite3.Row)
  with closing(sqlite3.connect(path))as holder:
   holder.execute('BEGIN IMMEDIATE')
   with ThreadPoolExecutor(max_workers=1)as pool,patch.object(mail,'sqlite3',fake_sqlite),patch.object(mail,'time',SimpleNamespace(time=lambda:clock[0])):
    future=pool.submit(method,*args)
    assert entered.wait(3),'Owned contender did not reach the writer'
    clock[0]=DEADLINE if expired else DEADLINE-1;holder.commit()
    try:future.result(timeout=4);accepted=True;error=None
    except mail.MailError as e:accepted=False;error=e.code
  with closing(sqlite3.connect(path))as db:
   after=list(db.iterdump());balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
   row=db.execute('SELECT read_at,claimed_at,deleted_at FROM game_mail WHERE id=?',(mid,)).fetchone()
  if action in ('claim','read')and expired:
   if report['baseline']:
    assert accepted and len(called)==1
    assert (balance==900 if action=='claim'else row[0]==DEADLINE-2)
   else:assert not accepted and error==2985 and not called and before==after and balance==0
  elif action=='delete':
   if report['baseline']:assert not accepted and error==2969 and before==after
   else:assert accepted and row[2]==DEADLINE and balance==0
  else:
   assert accepted and balance==900 and row[1]==(DEADLINE-2 if report['baseline']else DEADLINE-1)
   # A second current claim is an absolute receipt, never another grant.
   mail.claim(path,1,uid,[mid],encode,now=DEADLINE-1)
   with closing(sqlite3.connect(path))as db:
    assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(900,)
    assert db.execute('SELECT count(*) FROM game_mail_claims').fetchone()==(1,)
  report['cases'].append(dict(action=action,expired_during_writer_wait=expired,accepted=accepted,error=error,
      ED=balance,mail_timestamps=row,SQL_unchanged=before==after))
report.update(passed=True,owned_temporary_directories_removed=True)
path=W/('mail-clock-'+('baseline'if report['baseline']else'fixed')+'-'+str(time.time_ns())+'.json')
path.write_text(json.dumps(report,indent=2),'utf8');print(json.dumps(dict(report,evidence=str(path))))
