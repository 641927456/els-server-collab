"""Current ordinary mail producers, timed item escrow and overdue return atomicity."""
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,json,os,sqlite3,sys,tempfile,time
W=Path(__file__).resolve().parent;B=Path(os.environ['ELS_FULL_SOURCE']).resolve()
baseline='--baseline'in sys.argv
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor')]
import els_server,els_server.storage,els_server.domain
def module(name):
 relative=Path('els_server/storage')/(name+'.py');p=(B if baseline else W/'source')/relative
 spec=importlib.util.spec_from_file_location('els_server.storage.'+name,p)
 result=importlib.util.module_from_spec(spec);sys.modules[spec.name]=result;spec.loader.exec_module(result)
 return result,p
mail,mail_source=module('game_mail');player,player_source=module('player_mail')
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.item_expiration import assign
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
DEADLINE=1900000000
report=dict(passed=False,baseline=baseline,production_database_access=False,actual_SQL_writer_competition=True,
            source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in (mail_source,player_source)},cases=[])
def race(path,module,function,args,after):
 clock=[DEADLINE-2];entered=Event()
 class Waiting(sqlite3.Connection):
  def execute(self,sql,*args,**kwargs):
   if sql=='BEGIN IMMEDIATE':entered.set()
   return super().execute(sql,*args,**kwargs)
 def connect(*args,**kwargs):return sqlite3.connect(*args,**kwargs,factory=Waiting)
 with closing(sqlite3.connect(path))as holder:
  holder.execute('BEGIN IMMEDIATE')
  with ThreadPoolExecutor(max_workers=1)as pool,patch.object(module,'sqlite3',SimpleNamespace(connect=connect,Row=sqlite3.Row)),patch.object(module,'time',SimpleNamespace(time=lambda:clock[0])):
   future=pool.submit(function,*args);assert entered.wait(3);clock[0]=after;holder.commit()
   try:return True,future.result(timeout=4),None
   except ValueError as error:return False,None,error
def dump(path):
 with closing(sqlite3.connect(path))as db:return list(db.iterdump())
for action in ('send_expired','send_last_second','return_delete','return_encoder_failure'):
 with tempfile.TemporaryDirectory(prefix='owned-player-mail-clock-',dir=W)as name:
  path=Path(name)/'own.sqlite3';prepare(path);uids=[]
  for number in (1,2):
   roster=Characters(path,number);uid=roster.create('OwnMail'+str(number),1,'own-mail-'+str(number))['uid'];uids.append(uid)
   account=LocalAccount(LocalState(path,uid),account_id=number);account.enable_characters(characters=roster);account.get_inventory_snapshot()
   with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET ed=? WHERE uid=?',(1000000 if number==1 else 0,uid))
  mail.initialize(path);sender,target=uids
  request=dict(recipient='OwnMail2',title='Owned deadline',body='',ed=0,item=0,count=0,flag=0,extra=0)
  if action.startswith('send'):
   with closing(sqlite3.connect(path))as db,db:
    item=grant_items(db,[dict(template=77000,metadata=VERIFIED_TEMPLATES[77000],group=TEMPLATE_BAG_GROUPS[77000],quantity=7)],sender)[0]
    assign(db,sender,item['uid'],DEADLINE)
    other_items=[i for i in load_items(db,sender)if i['uid']!=item['uid']]
   request.update(item=item['uid'],count=7);before=dump(path)
   accepted,value,error=race(path,player,player.send,(path,1,sender,request,'owned-timed-mail',lambda value:value),DEADLINE+1 if action=='send_expired'else DEADLINE)
   if action=='send_expired'and not baseline:
    assert not accepted and 'expired'in str(error).lower()and dump(path)==before
   else:
    assert accepted,str(error)
    with closing(sqlite3.connect(path))as db:
     moved=db.execute('SELECT item_uid,item_json FROM player_mail_items').fetchone()
     assert moved[0]==item['uid']and json.loads(moved[1])['expires_at']==DEADLINE
     assert load_items(db,sender)==other_items
     created=db.execute('SELECT created_at FROM game_mail WHERE id=?',(value['mail_id'],)).fetchone()[0]
     assert created==(DEADLINE-2 if baseline else DEADLINE)
    player.send(path,1,sender,request,'owned-timed-mail',lambda value:value,now=DEADLINE)
    with closing(sqlite3.connect(path))as db:assert db.execute('SELECT count(*) FROM game_mail').fetchone()==(1,)
  else:
   request.update(ed=900)
   mid=player.send(path,1,sender,request,'owned-return-clock',lambda value:value,now=DEADLINE-player.ORDINARY_RETENTION)['mail_id']
   before=dump(path)
   def encode(ids):
    if action=='return_encoder_failure':raise ValueError('Owned deliberate response failure')
    return ids
   accepted,value,error=race(path,mail,mail.delete,(path,2,target,[mid],encode),DEADLINE)
   if baseline:assert not accepted and getattr(error,'code',None)==2969 and dump(path)==before
   elif action=='return_encoder_failure':assert not accepted and str(error)=='Owned deliberate response failure'and dump(path)==before
   else:
    assert accepted,str(error)
    with closing(sqlite3.connect(path))as db:
     returned=db.execute('SELECT mail_id FROM player_mail_meta WHERE return_of=?',(mid,)).fetchone()[0]
     assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(target,)).fetchone()==(0,)
     assert db.execute('SELECT ed,created_at FROM game_mail WHERE id=?',(returned,)).fetchone()==(900,DEADLINE)
     assert db.execute('SELECT returned_to FROM player_mail_meta WHERE mail_id=?',(mid,)).fetchone()==(returned,)
     balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(sender,)).fetchone()[0]
    for _ in range(2):mail.claim(path,1,sender,[returned],lambda *args:args,now=DEADLINE+1)
    with closing(sqlite3.connect(path))as db:
     assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(sender,)).fetchone()==(balance+900,)
     assert db.execute('SELECT count(*) FROM game_mail_claims').fetchone()==(1,)
  report['cases'].append(dict(action=action,accepted=accepted,error=str(error)if error else None,SQL_unchanged=dump(path)==before))
report.update(passed=True,owned_temporary_directories_removed=True)
p=W/('player-mail-clock-'+('baseline'if baseline else'fixed')+'-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2),'utf8');print(json.dumps(dict(report,evidence=str(p))))
