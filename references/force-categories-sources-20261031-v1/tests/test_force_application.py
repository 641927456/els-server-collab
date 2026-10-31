"""Exercise the real Application dispatch on a new owned SQLite only."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,json,sqlite3,struct,sys
import test_force_sources as t
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.protocol.protocol_codec import Event
from els_server.storage.native_force_exchange import exchange

case=t.Sources();case.setUp();runner=asyncio.Runner();app=None;packets=[]
try:
 case.town(20010)
 app=Application(ServerConfig(state_file=case.path,log_dir=case.path.parent/'logs'));app.account=case.account;s=runner.run(app.session());s.item_test=s.shop_test=True;s.role='game';s.phase='town_ready';s.completed={0x28,0x225,0x227};s.active_map=s.pending_map=20010
 from els_server.domain.normal_fatigue_flow import synchronization
 from els_server.domain.raid_reward_flow import synchronize
 runner.run(app.call(synchronization,s,[]));runner.run(app.call(synchronize,s,[]));seq=0
 def send(kind,payload):
  global seq
  seq+=1;out=runner.run(app.call(s.handle,Event(0x202,kind=kind,payload=payload,performers=(0,)),seq));packets.extend(dict(kind=e.kind,payload=e.payload.hex())for e in out if e.kind in(0x6cb,0x6d1,0x123));assert out and out[0].payload[:4]==bytes(4),(kind,[(e.kind,e.payload[:12].hex())for e in out]);return out
 r=next(r for r in t.catalog()['exchanges']if r['destination']==43959);case.seed(r['source'],r['source_quantity']);send(0x223,case.payload(r))
 with closing(sqlite3.connect(case.path))as db:item=next(i for i in t.load_items(db,1001)if i['template']==43959)
 payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0);before=case.dump()
 with patch('els_server.storage.boosting_2026_force_inventory.COMMON_LEARNING_ENABLED',False):
  with case.assertRaises(ValueError):t.base.use_book(case.path,1001,1,payload,'closed',now=t.NOW)
 case.assertEqual(case.dump(),before)
 send(0x219,payload);rule=next(r for r in t.catalog()['books']if r['item']==43959);send(0x122,struct.pack('>ii',10,rule['skill']))
 item=case.seed(43678);send(0x219,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0));rule=next(r for r in t.catalog()['books']if r['item']==43678);send(0x6d0,struct.pack('>iiiB',1,0,rule['skill'],rule['native_rank']))
 item=case.seed(300550);send(0x219,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0));send(0x6d0,struct.pack('>iiiB',2,0,901012,1))
 (t.base.HOME/'application-packets.json').write_text(json.dumps(packets),encoding='utf8')
 result=dict(ok=True,actual_Application=True,requests=seq,new_exchange_learning_hotbar=True,new_passive_and_Mod=True,forward_reader_recovery_gate=True,natural_GUI=False)
 (t.base.HOME/('application-'+('online'if 'online'in str(t.base.args.runtime)else'local')+'-result.json')).write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))
finally:
 if app:app.executor.shutdown(wait=True)
 runner.close();case.doCleanups()
