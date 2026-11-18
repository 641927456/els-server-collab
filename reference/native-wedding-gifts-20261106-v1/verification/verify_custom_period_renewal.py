"""Owned fixture: authenticated104 first wear, pending storage, rollback and expiry."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback,uuid
R=Path('G:/els');G=Path(__file__).resolve().parent;W=G.parents[1];B=G/'test-source-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(W/'delivery-duel-v1')]
ctypes.WinDLL(str(W/'duel-wire-v2/full-source/python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import insert,next_uid
from els_server.storage import item_expiration,wear_moves,bank_state
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,FASHION_EQUIP_SLOTS,item_body
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data
from create_friends_certificate import create
from native_peer import connect

from els_server.storage import character_custom as custom,custom_periods
from els_server.domain import character_custom as rules
from els_server.domain.custom_periods import value as period_value
from els_server.protocol import character_custom_messages as wire
from els_server.protocol.protocol_codec import encode_event

async def main():
 report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,actual_authenticated_TLS=False)
 with tempfile.TemporaryDirectory(prefix='owned-period-renewal-',dir=G)as name:
  private=Path(name).resolve();create(private,'127.0.0.1');dbfile=private/'game.sqlite3'
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=dbfile,accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  app=Application(cfg)
  try:
   await app.start();identity=app.registry.create('ownedperiodrenewal');uid=Characters(dbfile,identity['id']).create('RenewPeriod',1,'owned-renewal-character')['uid']
   def facts():
    with closing(sqlite3.connect(dbfile))as db:return tuple(db.iterdump())
   fixtures=[]
   with closing(sqlite3.connect(dbfile))as db,db:
    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');occupied={i['slot']for i in load_items(db,uid)if i['group']==4}
    for _ in range(2):
     slot=next(s for s in range(24)if s not in occupied);occupied.add(slot);item=dict(uid=next_uid(db),template=277156,metadata=0,count=1,group=4,slot=slot);insert(db,uid,item);fixtures.append(item)
   now=int(time.time());deadline=now+30*86400;payload=lambda item:struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
   custom.use_book(dbfile,uid,identity['id'],payload(fixtures[0]),'owned-renewal-first',now=now)
   v=period_value(14102,now,deadline);custom.select(dbfile,uid,identity['id'],wire.selection_map({7:v}),'owned-renewal-first-select',now=now)
   with closing(sqlite3.connect(dbfile))as db:
    assert custom.snapshot(db,uid,deadline+1)['selected']=={}
    assert db.execute('SELECT custom_id FROM character_custom_permanent_selection_slots WHERE owner=?AND slot=7',(uid,)).fetchone()==(14102,)
   before=facts()
   with patch.object(custom,'_commit',side_effect=ValueError('owned deliberate post-renewal receipt failure')):
    try:custom.use_book(dbfile,uid,identity['id'],payload(fixtures[1]),'owned-renewal-second',now=deadline+1)
    except ValueError as e:assert str(e)=='owned deliberate post-renewal receipt failure'
    else:raise AssertionError('Failed renewal receipt committed')
   assert facts()==before
   custom.use_book(dbfile,uid,identity['id'],payload(fixtures[1]),'owned-renewal-second',now=deadline+1)
   with closing(sqlite3.connect(dbfile))as db:
    state=custom.snapshot(db,uid,deadline+1);assert state['selected']=={}and state['owned'][7]==[period_value(14102,deadline+1,deadline+1+30*86400)]
    assert not db.execute('SELECT 1 FROM character_custom_permanent_selection_slots WHERE owner=?AND slot=7',(uid,)).fetchone()
   stable=facts();assert custom.use_book(dbfile,uid,identity['id'],payload(fixtures[0]),'owned-renewal-first',now=deadline+2)['replayed']and facts()==stable
   report.update(ok=True,checks=['A stale expired saved selection remains hidden after cold read; renewing the same sit starts a new30day period without automatically selecting it','A late receipt failure rolls back source debit, renewed ownership and removal of expired selection','Replaying the older registration after renewal cannot extend or replace the new deadline'],source_sha256=hashlib.sha256(Path(custom_periods.__file__).read_bytes()).hexdigest())
  finally:app.close()
 report['owned_private_directory_removed']=not private.exists()
 out=G/('custom-period-renewal-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out))))
asyncio.run(main())
