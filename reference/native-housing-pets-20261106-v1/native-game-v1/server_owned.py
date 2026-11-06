"""One owned native client over a previously prepared, owned permanent house."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,time,traceback
HERE=Path(__file__).resolve().parent
binding=json.loads((HERE/'runtime-binding.json').read_bytes());runtime=Path(binding['runtime']);source=Path(binding['candidate_server_overlay']).parent
attempt=Path(sys.argv[1]).resolve();assert attempt.parent==HERE and int(sys.argv[2])==1
sys.dont_write_bytecode=True
sys.path[:0]=[str(source),str(runtime),str(runtime/'vendor'),str(runtime/'tools'),'G:/els/tools/pylibs','G:/els/tools','G:/els',str(HERE.parents[1]/'delivery-duel-v1')]
ctypes.WinDLL(str(runtime/'python/sqlite3.dll'))
from els_server.application import Application,FriendsSession
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.town_travel import catalog
from els_server.storage.inventory_state import grant_items
from els_server.storage import companion_state,pet_progression,housing_pets
from els_server.protocol.housing_layout_messages import REQUEST,encode
from native_peer import Peer,connect
from create_friends_certificate import create
def save(p,v):
 q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(v,indent=2)+'\n','utf8');q.replace(p)

async def main():
 pins=json.loads((HERE/'server-source-pins.json').read_bytes());assert len(pins)==1608
 for rel,digest in pins.items():assert hashlib.sha256((source/rel).read_bytes()).hexdigest()==digest,rel
 private=attempt/'private';private.mkdir(exist_ok=False);create(private,'127.0.0.1')
 cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,normal_equipment_moves_enabled=True,
  state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
  tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=attempt/'server-logs')
 app=Application(cfg);server=None;peers=[];observed=[];errors=[];stage='setup';original=FriendsSession.handle;identity=None;entry_town=None
 def read(query,values=()):
  with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(query,values).fetchall()
 def track(s,event,*args,**kw):
  nonlocal entry_town
  if identity is not None and s.account.account_id==identity['id']and event.kind in(0x923,0x92e,0xa38,0xa3a,0x225,0x227):
   observed.append(dict(kind=event.kind,size=len(event.payload),phase=s.phase,time=time.monotonic()))
   if event.kind==0x923:entry_town=read('SELECT town FROM location WHERE uid=?',(s.account.uid,))[0][0]
  return original(s,event,*args,**kw)
 try:
  await app.start();identity=app.registry.create('ownedhousingnative')
  uid=Characters(cfg.state_file,identity['id']).create('OwnHome',1,'owned-native-housing')['uid'];pet_uid=90000001
  LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
  with closing(sqlite3.connect(cfg.state_file))as db,db:
   db.execute('BEGIN IMMEDIATE');companion_state.ensure(db)
   db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET ed=60000000 WHERE uid=?',(uid,))
   db.execute('INSERT INTO companions VALUES (?,?,?,?,?,?)',(pet_uid,uid,'pet',1,'HomePet',0))
   pet=companion_state.rows(db,uid,'pet')[0];pet.update(step=3,growth=0);pet_progression.save(db,uid,pet)
   contract=grant_items(db,[dict(template=713275,metadata=0,group=4,quantity=1)],uid)[0]
  FriendsSession.handle=track
  server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
  _,port=await server.start();cert=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
  bridge=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=cert)
  peer=await connect(dict(uid=uid,bridge=bridge),peers)
  stage='preparing_owned_house'
  assert (await peer.query(0x219,struct.pack('>QQiiIB',contract['uid'],0,0,0,0,0))).payload[:4]==bytes(4)
  assert (await peer.query(0xea,struct.pack('>BHIiii',0,0,1,570234,1,10018))).payload[:4]==bytes(4)
  mat_uid=read('SELECT uid FROM inventory_items WHERE owner=? AND template=570234',(uid,))[0][0]
  assert (await peer.query(0x923,struct.pack('>Qi3fB',0,26000,0,0,0,1))).payload[:4]==bytes(4)
  # Original244D4A0 applies grid furniture through2451350, which assigns
  # the active pet mat.244D960 free-position furniture has a separate path.
  rows=[(mat_uid,(2,mat_uid,570234,0,0,0))]
  assert (await peer.query(0x935,encode(REQUEST,(rows,[],[],0,0,0)))).payload[:4]==bytes(4)
  await peer.close();peers.remove(peer)
  async with asyncio.timeout(8):
   while identity['id']in app.playing:await asyncio.sleep(.01)
  baseline=read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid');inventory=read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')
  observed.clear();save(private/'bridge.json',bridge)
  save(attempt/'server-ready.json',dict(uid=uid,pet_uid=pet_uid,mat_uid=mat_uid,account=identity['id'],family=1,
   production_database_access=False,minimum_scene_seconds=120,source_pins_sha256=binding['source_pins_sha256']))
  stage='waiting_native';began=time.monotonic();status={}
  while not(attempt/'server.stop').exists()and time.monotonic()-began<300:
   s=app.playing.get(identity['id']);phase=None if s is None else s.phase
   with closing(sqlite3.connect(cfg.state_file))as db:placed=housing_pets.saved(db,uid)
   status=dict(phase=phase,placed=[r[2]for r in placed],events=observed,errors=errors,observed_seconds=time.monotonic()-began)
   save(attempt/'status.json',status)
   marker=attempt/'native-observer-complete.json'
   failure=attempt/'native-observer-failure.json'
   if failure.exists():raise RuntimeError('Owned native observer failed: '+failure.read_text('utf8'))
   if marker.exists():
    done=json.loads(marker.read_bytes());assert done['ok']and done['uid']==str(uid)
    assert phase=='housing_ready'and not placed and {0x923,0x92e,0xa38,0xa3a}.issubset({r['kind']for r in observed})
    assert read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')==baseline
    assert read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')==inventory
    assert entry_town is not None and read('SELECT town FROM location WHERE uid=?',(uid,))==[(entry_town,)]
    with closing(sqlite3.connect(cfg.state_file))as db:assert companion_state.rows(db,uid,'pet')[0]['growth']==0
    save(attempt/'scenario-complete.json',dict(ok=not errors,**status,native=done));break
   await asyncio.sleep(.25)
  save(attempt/'server-result.json',dict(ok=(attempt/'scenario-complete.json').exists()and not errors,
   **status,natural_GUI=False,client_transport_signed=True,candidate_server_installed=False))
 except BaseException:
  save(attempt/'server-failure.json',dict(stage=stage,error=traceback.format_exc()));raise
 finally:
  FriendsSession.handle=original
  for peer in reversed(peers):await peer.close()
  if server is not None:await server.close()
  app.close()
if __name__=='__main__':asyncio.run(main())
