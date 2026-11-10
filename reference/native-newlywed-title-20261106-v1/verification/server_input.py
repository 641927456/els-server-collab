"""Owned town fixture for the current server period wire and native formatter."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,time,traceback
N=Path(sys.argv[1]).resolve();P=N.parents[1];W=P.parents[1];R=Path('G:/els');settings=json.loads((N/'settings.json').read_bytes());runtime=Path(settings['runtime']);source=P.parent/'period-wire-v4/test-source-v1'
assert N.parent==P/'native-game-v1'and int(sys.argv[2])==1
sys.dont_write_bytecode=True;sys.path[:0]=[str(source),str(runtime),str(runtime/'vendor'),str(runtime/'tools'),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
ctypes.WinDLL(str(runtime/'python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import next_uid,insert
from els_server.domain.inventory_items import item_body,fixture
from els_server.domain.town_travel import catalog
from create_friends_certificate import create

def save(name,value):
 p=N/name;q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(value,indent=2)+'\n','utf8');q.replace(p)
from els_server.domain.local_session import LocalSession
original_responses=LocalSession.responses
def traced_responses(self,kind):
 replies=original_responses(self,kind)
 if kind==0x1ef:
  rows=[dict(event_id=e.event_id,kind=e.kind,payload_bytes=len(e.payload),numeric_seconds=struct.unpack_from('>Q',e.payload,42)[0] if len(e.payload)>=50 else None,date=e.payload[4:42].decode('utf-16le') if len(e.payload)>=42 else None) for e in replies]
  with (N/'clock-server.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(dict(build=self.client_build,phase=self.phase,replies=rows))+'\n')
 return replies
LocalSession.responses=traced_responses

async def main():
 private=N/'private';private.mkdir();create(private,'127.0.0.1')
 cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=N/'server-logs')
 app=Application(cfg);server=None;errors=[];stage='setup'
 try:
  await app.start();identity=app.registry.create('ownedperiodnative');uid=Characters(cfg.state_file,identity['id']).create('OwnPeriod',1,'owned-native-period')['uid']
  LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz']);samples=[];now=int(time.time())
  with closing(sqlite3.connect(cfg.state_file))as db,db:
   db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');occupied={i['slot']for i in load_items(db,uid)if i['group']==7}
   for name,period,deadline in(('pending1',86400,None),('pending30',30*86400,None),('active30',None,now+30*86400),('permanent',None,None)):
    slot=next(s for s in range(24)if s not in occupied);occupied.add(slot);item=dict(uid=next_uid(db),template=277170,metadata=0,count=1,group=7,slot=slot)
    if period:item['activation_seconds']=period
    if deadline:item['expires_at']=deadline
    insert(db,uid,item);samples.append(dict(name=name,uid=item['uid'],template=item['template'],metadata=item['metadata'],group=item['group'],body_hex=item_body(item).hex()))
  marker=next(f['wire_offset']for f in fixture()['fields']if int(f['offset'],0)==0x34e)
  active=next(s for s in samples if s['name']=='active30')
  for name,day in(('active_control0',0),('active_marker1',1),('active_marker_max',32767)):
   body=bytearray.fromhex(active['body_hex']);struct.pack_into('>h',body,marker,day);samples.append(dict(active,name=name,body_hex=body.hex()))
  def facts():
   with closing(sqlite3.connect(cfg.state_file))as db:return dict(inventory=db.execute('SELECT *FROM inventory_items ORDER BY uid').fetchall(),balances=db.execute('SELECT *FROM reward_balances ORDER BY uid').fetchall(),activation=db.execute('SELECT *FROM item_activation_periods ORDER BY item_uid').fetchall(),deadlines=db.execute('SELECT *FROM item_expiration ORDER BY item_uid').fetchall())
  baseline=facts();server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None);_,port=await server.start()
  bridge=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest());(private/'bridge.json').write_text(json.dumps(bridge),'utf8')
  save('server-ready.json',dict(uid=uid,family=1,samples=samples,minimum_scene_seconds=120,active_deadline=now+30*86400,production_database_access=False,source_pins={p.relative_to(P.parent/'period-wire-v4/candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(P.parent/'period-wire-v4/candidate').rglob('*')if p.is_file()}));stage='waiting_native';start=time.monotonic()
  while not(N/'server.stop').exists()and time.monotonic()-start<300:
   s=app.playing.get(identity['id']);phase=None if s is None else s.phase;save('status.json',dict(phase=phase,seconds=time.monotonic()-start,errors=errors))
   if(N/'native-observer-failure.json').exists():raise ValueError('Owned native period observer failed')
   if(N/'native-observer-complete.json').exists():
    result=json.loads((N/'native-observer-complete.json').read_bytes());assert result['ok']and phase=='town_ready'and not errors and facts()==baseline
    save('scenario-complete.json',dict(ok=True,phase=phase,native=result,inventory_and_economy_unchanged=True,natural_GUI=False));break
   await asyncio.sleep(.25)
  save('server-result.json',dict(ok=(N/'scenario-complete.json').exists(),errors=errors,natural_GUI=False))
 except BaseException:save('server-failure.json',dict(stage=stage,error=traceback.format_exc()));raise
 finally:
  if server is not None:await server.close()
  app.close()
asyncio.run(main())
