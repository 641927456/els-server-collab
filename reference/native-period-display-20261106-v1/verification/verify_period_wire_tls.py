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

async def main():
 report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,production_database_access=False,checks=[])
 app=server=None;peers=[];errors=[];stage='setup'
 with tempfile.TemporaryDirectory(prefix='owned-period-wire-',dir=G)as name:
  private=Path(name).resolve();create(private,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  try:
   app=Application(cfg);await app.start();identity=app.registry.create('ownedfirstuse')
   uid=Characters(cfg.state_file,identity['id']).create('FirstUse',1,'owned-first-use')['uid']
   LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
   def items():
    with closing(sqlite3.connect(cfg.state_file))as db:return load_items(db,uid)
   def owned(item_uid):return next(i for i in items()if i['uid']==item_uid)
   def facts():
    with closing(sqlite3.connect(cfg.state_file))as db:
     return {t:db.execute('SELECT *FROM '+t+' ORDER BY 1').fetchall()for t in('inventory_items','item_activation_periods','item_expiration','wear_move_receipts')if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(t,)).fetchone()}
   fixtures=[]
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
    occupied={i['slot']for i in load_items(db,uid)if i['group']==7}
    for period in(30*86400,86400,None):
     slot=next(s for s in range(24)if s not in occupied);occupied.add(slot)
     item=dict(uid=next_uid(db),template=306699,metadata=0,count=1,group=7,slot=slot)
     if period:item['activation_seconds']=period
     insert(db,uid,item);fixtures.append(item)
   assert all(owned(i['uid'])==i for i in fixtures)
   # The original private bank flags decide admission; the container writer
   # preserves the whole pending instance rather than starting its timer.
   source=fixtures[1];assert not client_data().item(source['template'])['flags4']&32
   request=lambda sg,ss,dg,ds:struct.pack('>BiBiiQi',sg,ss,dg,ds,1,0,source['template'])
   bank_state.transfer(cfg.state_file,uid,request(7,source['slot'],8,0),'owned-pending-bank-in')
   with closing(sqlite3.connect(cfg.state_file))as db:
    assert bank_state.load(db,uid)[0]['item']==source
    assert not db.execute('SELECT 1 FROM item_activation_periods WHERE item_uid=?',(source['uid'],)).fetchone()
   bank_state.transfer(cfg.state_file,uid,request(8,0,7,source['slot']),'owned-pending-bank-out')
   assert owned(source['uid'])==source
   report['checks'].append('Pending1/30day periods survive cold reads; original bank transfer preserves UID and pending seconds without starting the timer')
   from els_server.storage.mail_attachments import qualify as mail_qualify
   from els_server.storage.trade_board_state import _normal_sale_item
   from els_server.domain.item_expiration import MAXIMUM,native_period_days
   from role_native_replay import Replay
   native=Replay();native_rows=[]
   clock=int(time.time());sample=fixtures[0]
   cases=[('permanent',{k:v for k,v in sample.items()if k!='activation_seconds'},0),('pending30',sample,30),('pending1',fixtures[1],1)]
   for delta in(-1,0,1,86400,30*86400,MAXIMUM-clock):
    value={k:v for k,v in sample.items()if k!='activation_seconds'};value['expires_at']=clock+delta
    cases.append(('active:'+str(delta),value,min(32767,max(1,delta//86400+1))))
   for label,item,expected in cases:
    with patch('els_server.domain.item_expiration.time.time',return_value=clock):raw=item_body(item)
    parsed=native.item(raw);assert parsed['ok']==1 and parsed['consumed']==len(raw)
    dto=bytes.fromhex(parsed['dto']);assert struct.unpack_from('<h',dto,0x34e)[0]==expected
    assert native_period_days(item,now=clock)==expected
    native_rows.append(dict(case=label,day_marker=expected,wire_bytes=len(raw)))
   for timed in(sample,dict(fixtures[2],expires_at=clock+86400)):
    try:mail_qualify(timed,now=clock)
    except ValueError as error:assert str(error)=='Periodic equipment cannot be mailed'
    else:raise AssertionError('Native-refused periodic equipment admitted to mail')
   stone=dict(uid=123456789,template=109945,metadata=2,count=1,group=4,slot=23)
   assert mail_qualify(stone,now=clock)==mail_qualify(dict(stone,expires_at=clock+86400),now=clock)
   with closing(sqlite3.connect(cfg.state_file))as db:
    try:_normal_sale_item(db,uid,sample,1,0,load_items(db,uid),clock)
    except ValueError as error:assert 'timed/unidentified/hanger'in str(error)
    else:raise AssertionError('Unstarted periodic trade source admitted')
   report['native_D9A550_rows']=native_rows
   report['checks'].append('Original D9A550 accepts permanent0, unstarted1/30 and dated positive signed-day markers; exact date field/expiry remains unchanged, including long valid deadlines')
   report['checks'].append('Mail refuses timed usage0/1 equipment like original2DE6950 and retains usage2 material eligibility; shared market/personal trade guard refuses unstarted timed items')

   server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
   _,port=await server.start();bridge=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
   actor=dict(uid=uid,bridge=bridge);peer=await connect(actor,peers)
   wear=lambda sg,ss,dg,ds:struct.pack('>BiBiB',sg,ss,dg,ds,0)
   slot=FASHION_EQUIP_SLOTS[306699];source=fixtures[0]
   stage='authenticated first wear'
   begin=int(time.time());answer=await peer.query(0x104,wear(7,source['slot'],9,slot));end=int(time.time())
   assert answer.payload[-4:]==bytes(4)
   active=owned(source['uid']);deadline=active['expires_at']
   assert 'activation_seconds'not in active and begin+30*86400<=deadline<=end+30*86400
   assert(active['group'],active['slot'])==(9,slot)
   # A fresh unequip/equip must retain the original deadline and exact UID.
   assert(await peer.query(0x104,wear(9,slot,7,source['slot']))).payload[-4:]==bytes(4)
   assert(await peer.query(0x104,wear(7,source['slot'],9,slot))).payload[-4:]==bytes(4)
   assert owned(source['uid'])['expires_at']==deadline
   await peer.close();peers.remove(peer)
   async with asyncio.timeout(8):
    while identity['id']in app.playing:await asyncio.sleep(.01)
   peer=await connect(actor,peers);assert owned(source['uid'])==active
   report['checks'].append('Actual authenticated104/105 starts30days on first wear; repeated wear and cold reauthentication retain the same UID/deadline')
   # Use the same production writer with a deliberately failed late consumer.
   stage='late prepare rollback and durable replay'
   source=fixtures[1];session=str(uuid.uuid4());payload=wear(7,source['slot'],9,slot);before=facts()
   def fail(*args):raise ValueError('owned deliberate late prepare failure')
   try:wear_moves.move(cfg.state_file,payload,uid,account_id=identity['id'],session_id=session,sequence=1,prepare=fail)
   except ValueError as e:assert str(e)=='owned deliberate late prepare failure'
   else:raise AssertionError('Late prepare failure committed')
   assert facts()==before and owned(source['uid'])==source
   first=wear_moves.move(cfg.state_file,payload,uid,account_id=identity['id'],session_id=session,sequence=1)
   current=owned(source['uid']);assert 'activation_seconds'not in current and current['expires_at']>=begin+86400
   stable=facts();second=wear_moves.move(cfg.state_file,payload,uid,account_id=identity['id'],session_id=session,sequence=1)
   assert first==second and facts()==stable
   report['checks'].append('Late prepare rejection rolls back timer, positions and receipts; exact operation replay returns current response with no extra activation')
   stage='original permanent wear and expiry cleanup'
   permanent=fixtures[2]
   answer=await peer.query(0x104,wear(7,permanent['slot'],9,slot));assert answer.payload[-4:]==bytes(4)
   assert 'expires_at'not in owned(permanent['uid'])and'activation_seconds'not in owned(permanent['uid'])
   events=item_expiration.remove_due(cfg.state_file,uid,now=deadline+1)
   assert events and not any(i['uid']in{fixtures[0]['uid'],fixtures[1]['uid']}for i in items())
   assert owned(permanent['uid'])['group']==9
   with closing(sqlite3.connect(cfg.state_file))as db:
    assert not db.execute('SELECT 1 FROM item_activation_periods WHERE item_uid IN(?,?)',(fixtures[0]['uid'],fixtures[1]['uid'])).fetchone()
    assert not db.execute('SELECT 1 FROM item_expiration WHERE item_uid IN(?,?)',(fixtures[0]['uid'],fixtures[1]['uid'])).fetchone()
   assert not errors
   report['checks'].append('Permanent wearing stays permanent; existing expiry sweep removes both activated items and their child rows while retaining permanent wear')
   report.update(ok=True,source_pins={p.relative_to(G/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(G/'candidate').rglob('*')if p.is_file()})
  except BaseException:report.update(stage=stage,error=traceback.format_exc())
  finally:
   for peer in reversed(peers):await peer.close()
   if server is not None:await server.close()
   if app is not None:app.close()
 report.update(owned_private_directory_removed=not private.exists(),owned_listeners_closed=True)
 out=G/('period-wire-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(main()))
