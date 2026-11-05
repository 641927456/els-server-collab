"""Real guild deposit waiting for a writer crosses an item's native deadline."""
import os,sys
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_FULL_SOURCE']).resolve()
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor'),'G:/els/tools/pylibs']
import ctypes
_sqlite_runtime=ctypes.WinDLL(str(BASE/'python/sqlite3.dll'))
import els_server,els_server.domain,els_server.storage,els_server.protocol
env=SimpleNamespace(HERE=HERE)

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import hashlib,importlib.util,json,sqlite3,struct,sys,tempfile,time
from els_server.domain.local_session import LocalAccount
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import guild_membership_state as members
from els_server.domain.guild_initial_profile import profile
from els_server.protocol import guild_membership_profile as wire
from els_server.protocol.social_messages import wstring
source=env.HERE/('baseline'if '--baseline'in sys.argv else'source')/'els_server/storage/guild_bank_items.py'
spec=importlib.util.spec_from_file_location('els_server.storage.guild_bank_items',source)
bank=importlib.util.module_from_spec(spec);sys.modules[spec.name]=bank;spec.loader.exec_module(bank)
START=1900000000;deadline=START+100
report=dict(passed=False,baseline='--baseline'in sys.argv,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),cases=[],production_database_access=False)
for expire in(True,False):
 with tempfile.TemporaryDirectory(prefix='owned-guild-bank-clock-',dir=env.HERE)as tmp:
  path=Path(tmp)/'own.sqlite3';prepare(path);roster=Characters(path,1);uid=roster.create('OwnBankClock',1,'own-bank-clock-create')['uid']
  account=LocalAccount(LocalState(path,uid),account_id=1);account.enable_characters(characters=roster);account.get_inventory_snapshot()
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
   license=grant_items(db,[dict(template=110845,metadata=0,group=4,quantity=1)],uid)[0]
   payload=struct.pack('>Q',license['uid'])+wstring('OwnBankClock')+wstring('')
   members.create(db,uid,1,license['uid'],'OwnBankClock','',payload,'own-guild-create',START,
    encode=lambda saved,changes,repeat:[wire.full_notification(profile(saved))],guard=lambda:None)
   item=grant_items(db,[dict(template=701000,metadata=2,group=3,quantity=10,expires_at=deadline)],uid)[0]
  with closing(sqlite3.connect(path))as db:before=list(db.iterdump())
  entered=ThreadEvent();clock=[deadline-1]
  class Waiting(sqlite3.Connection):
   def execute(self,sql,*a,**kw):
    if sql=='BEGIN IMMEDIATE':entered.set()
    return super().execute(sql,*a,**kw)
  def connect(*a,**kw):return sqlite3.connect(*a,**kw,factory=Waiting)
  payload=struct.pack('>QiQ',item['uid'],10,2**64-1)
  with closing(sqlite3.connect(path))as holder:
   holder.execute('BEGIN IMMEDIATE')
   with ThreadPoolExecutor(max_workers=1)as pool,patch.object(bank,'sqlite3',SimpleNamespace(connect=connect)),patch.object(bank,'time',SimpleNamespace(time=lambda:clock[0])):
    future=pool.submit(bank.perform,path,uid,1,0x50a,payload,'own-guild-deposit',lambda db:None)
    assert entered.wait(3)
    clock[0]=deadline+1 if expire else deadline
    holder.commit()
    try:future.result(timeout=4);accepted=True
    except ValueError as error:assert str(error)=='Item has expired',str(error);accepted=False
  with closing(sqlite3.connect(path))as db:
   after=list(db.iterdump());inventory=[i for i in load_items(db,uid)if i['uid']==item['uid']]
  if expire and not report['baseline']:assert not accepted and before==after and inventory[0]['count']==10
  else:assert accepted and before!=after and not inventory
  report['cases'].append(dict(expired_while_waiting=expire,accepted=accepted,SQL_unchanged=before==after))
report.update(passed=True,temporary_directories_removed=True)
p=env.HERE/('bank-clock-'+('baseline'if report['baseline']else'fixed')+'-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(report,evidence=str(p))))
