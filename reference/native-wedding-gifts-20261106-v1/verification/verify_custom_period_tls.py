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
 report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,production_database_access=False,checks=[])
 app=server=None;peers=[];errors=[];stage='setup'
 with tempfile.TemporaryDirectory(prefix='owned-custom-period-',dir=G)as name:
  private=Path(name).resolve();create(private,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  try:
   app=Application(cfg);await app.start();identity=app.registry.create('ownedcustomperiod')
   roster=Characters(cfg.state_file,identity['id']);uid=roster.create('CustomPeriod',1,'owned-custom-period')['uid']
   lu=roster.create('OldLuSit',10,'owned-old-lu-sit')['uid']
   for person in(uid,lu):LocalState(cfg.state_file,person).save(20001,0,0,catalog()['towns']['20001']['xyz'])
   def read(sql,args=()):
    with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
   def state(person=uid,at=None):
    with closing(sqlite3.connect(cfg.state_file))as db:return custom.snapshot(db,person,at)
   def facts():
    with closing(sqlite3.connect(cfg.state_file))as db:
     return {t:db.execute('SELECT *FROM '+t+' ORDER BY 1').fetchall()for t, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
   fixtures=[]
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');occupied={i['slot']for i in load_items(db,uid)if i['group']==4}
    for _ in range(2):
     slot=next(s for s in range(24)if s not in occupied);occupied.add(slot)
     item=dict(uid=next_uid(db),template=277156,metadata=0,count=1,group=4,slot=slot);insert(db,uid,item);fixtures.append(item)
    custom.initialize(db);custom.initialize_extra(db)
    corrections=rules.data()['sit_variant_corrections']['custom_ids']
    for cid in corrections:
     rule=next(r for r in rules.catalog().values()if cid in r['custom_ids']);assert rule['type']==7 and rule['units']==[10]
     db.execute('INSERT INTO character_custom_permanent VALUES(?,?,?)',(lu,cid,rule['book']))
    db.execute('INSERT INTO character_custom_permanent_extra_selection VALUES(?,?,?,?)',(lu,7,corrections[0],3))
   before=facts();old_state=state(lu);assert len(old_state['owned'][7])==49 and all(v['variant']==2 for v in old_state['owned'][7])
   assert old_state['selected'][7]['variant']==2 and facts()==before
   for v in old_state['owned'][7]:wire.info(v)
   assert roster.get(lu)['character_custom']['selected'][7]==old_state['selected'][7]
   report['checks'].append('All49 affected permanent Lu sits restore as native major variant2; old saved variant3 is projected correctly without rewriting ownership/receipts')
   stage='registration late encoder rollback'
   source=fixtures[0];payload=struct.pack('>QQiiIB',source['uid'],0,0,0,0,0);before=facts();real_encode=custom.encode_event
   def reject_registration(event):
    if event.kind==0x4cd:raise ValueError('owned deliberate registered encoder failure')
    return real_encode(event)
   with patch.object(custom,'encode_event',side_effect=reject_registration):
    try:custom.use_book(cfg.state_file,uid,identity['id'],payload,'owned-late-custom-failure')
    except ValueError as e:assert str(e)=='owned deliberate registered encoder failure'
    else:raise AssertionError('Failed custom encoder committed')
   assert facts()==before
   server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
   _,port=await server.start();bridge=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
   actor=dict(uid=uid,bridge=bridge);peer=await connect(actor,peers)
   stage='actual219 registration and4CB selection'
   begin=int(time.time());answer=await peer.query(0x219,payload);end=int(time.time());assert answer.payload[:4]==bytes(4)
   saved=read('SELECT custom_id,source_template,starts_at,expires_at FROM character_custom_periods WHERE owner=?',(uid,));assert len(saved)==1
   cid,book,start,deadline=saved[0];assert(cid,book)==(14102,277156)and begin<=start<=end and deadline-start==30*86400
   assert not read('SELECT 1 FROM inventory_items WHERE uid=?',(source['uid'],))
   v=period_value(cid,start,deadline);assert state()['owned'][7]==[v]
   assert any(e.kind==0x4cd and e.payload==wire.registered(v).payload for e in peer.received)
   answer=await peer.query(0x4cb,wire.selection_map({7:v}));assert answer.payload[:4]==bytes(4)
   assert state()['selected'][7]==v
   # Period dates are authority, not arbitrary client requests.
   bad=dict(v,date1=rules.DATE1,date2=rules.DATE2)
   try:wire.selection_map({7:bad})
   except ValueError:pass
   else:raise AssertionError('Permanent dates admitted for period custom')
   raw=bytearray(wire.selection_map({7:v}));struct.pack_into('>i',raw,len(raw)-4,2)
   before=facts();answer=await peer.query(0x4cb,bytes(raw));assert answer.payload[:4]!=bytes(4)and facts()==before
   source2=fixtures[1];second=struct.pack('>QQiiIB',source2['uid'],0,0,0,0,0)
   before=facts();answer=await peer.query(0x219,second);assert answer.payload[:4]!=bytes(4)and facts()==before
   report['checks'].append('Actual219/21A+4CD starts exactly30days at registration; original4CB/4CC+18E selects the owned dated tuple; incorrect side and active duplicate preserve inventory/deadline')
   operation=read("SELECT operation_id FROM inventory_action_receipts WHERE owner=?AND kind=537 ORDER BY rowid",(uid,))[0][0].removeprefix('custom-book:')
   before=facts();assert custom.use_book(cfg.state_file,uid,identity['id'],payload,operation)['replayed']and facts()==before
   await peer.close();peers.remove(peer)
   async with asyncio.timeout(8):
    while identity['id']in app.playing:await asyncio.sleep(.01)
   peer=await connect(actor,peers);assert state()['selected'][7]==v and state()['owned'][7]==[v]
   assert any(e.kind==0x2a for e in peer.received)
   await peer.close();peers.remove(peer)
   async with asyncio.timeout(8):
    while identity['id']in app.playing:await asyncio.sleep(.01)
   report['checks'].append('Exact registration replay adds no period or item; cold2A restore preserves dated ownership and selected sit')
   stage='expiry, rollback and replay after expiry'
   assert state(at=deadline)['selected'][7]==v
   assert not state(at=deadline+1)['owned'].get(7)and 7 not in state(at=deadline+1)['selected']
   before=facts()
   try:custom.select(cfg.state_file,uid,identity['id'],wire.selection_map({7:v}),'owned-expired-apply',now=deadline+1)
   except ValueError:pass
   else:raise AssertionError('Expired sit Apply succeeded')
   assert facts()==before
   import els_server.protocol.protocol_codec as codec
   real_encode=codec.encode_event
   def reject_notice(event):
    if event.kind==0x18e:raise ValueError('owned deliberate expiry encoder failure')
    return real_encode(event)
   with patch.object(codec,'encode_event',side_effect=reject_notice):
    try:custom_periods.expire(cfg.state_file,uid,now=deadline+1)
    except ValueError as e:assert str(e)=='owned deliberate expiry encoder failure'
    else:raise AssertionError('Failed expiry encoder committed')
   assert facts()==before
   events=custom_periods.expire(cfg.state_file,uid,now=deadline+1);assert[e.kind for e in events]==[0x4cc,0x18e]
   for event in events:encode_event(event)
   stable=facts();assert custom_periods.expire(cfg.state_file,uid,now=deadline+2)==[]and facts()==stable
   old=custom.use_book(cfg.state_file,uid,identity['id'],payload,operation,now=deadline+1);assert old['replayed']and all(e.kind!=0x4cd for e in old['events'])and facts()==stable
   assert read('SELECT starts_at,expires_at FROM character_custom_periods WHERE owner=?',(uid,))==[(start,deadline)]
   report['checks'].append('Exact expiry boundary matches native item time; expired ownership/selection disappear, Apply refuses, failed expiry notice rolls back, cleanup/replay never extends the period')
   assert not errors
   report.update(ok=True,period=dict(custom_id=cid,starts_at=start,expires_at=deadline),source_pins={p.relative_to(G/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(G/'candidate').rglob('*')if p.is_file()})
  except BaseException:report.update(stage=stage,error=traceback.format_exc())
  finally:
   for peer in reversed(peers):await peer.close()
   if server is not None:await server.close()
   if app is not None:app.close()
 report.update(owned_private_directory_removed=not private.exists(),owned_listeners_closed=True)
 out=G/('custom-period-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(main()))
