"""One owned native guest plus31 authenticated protocol actors; no player data."""
from pathlib import Path
from contextlib import closing
import asyncio, ctypes, faulthandler, hashlib, json, sqlite3, ssl, struct, sys, time, traceback

HERE=Path(__file__).resolve().parent
binding=json.loads((HERE/'runtime-binding.json').read_bytes())
runtime=Path(binding['runtime']);source=Path(binding['candidate_server_overlay']).parent
attempt=Path(sys.argv[1]).resolve();assert attempt.parent==HERE and int(sys.argv[2])==1
sys.dont_write_bytecode=True
sys.path[:0]=[str(source),str(runtime),str(runtime/'vendor'),str(runtime/'tools'),
 'G:/els/tools/pylibs','G:/els/tools','G:/els',str(HERE.parents[1]/'delivery-duel-v1')]
_sqlite=ctypes.WinDLL(str(runtime/'python/sqlite3.dll'))
from els_server.application import Application, FriendsSession
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import relationships
from els_server.protocol import relationship_messages as rel
from els_server.protocol.protocol_codec import decode_event,decode_frame
from els_server.protocol.social_messages import wstring
from els_server.domain.town_travel import catalog
from native_peer import Peer, connect
from create_friends_certificate import create

def save(path,value):
 p=path.with_suffix(path.suffix+'.tmp');p.write_text(json.dumps(value,indent=2)+'\n','utf8');p.replace(path)

original_close=Peer.close
async def receive(peer):
 try:
  while True:
   head=await peer.reader.readexactly(8)
   raw=head+await peer.reader.readexactly(struct.unpack_from('<I',head)[0]-8)
   e=decode_event(decode_frame(raw,peer.keys,expected_sequence=peer.incoming).plaintext)
   peer.incoming+=1;peer.received.append(e);peer._qa_queue.put_nowait(e)
 except (asyncio.IncompleteReadError,ConnectionError):return
async def until(peer,kind):
 if not hasattr(peer,'_qa_queue'):
  peer._qa_queue=asyncio.Queue();peer._qa_receiver=asyncio.create_task(receive(peer))
 async with asyncio.timeout(25):
  for _ in range(400):
   e=await peer._qa_queue.get()
   if e.kind==kind:return e
 raise AssertionError('Original peer reply absent '+hex(kind))
async def close(peer):
 try:return await original_close(peer)
 finally:
  if hasattr(peer,'_qa_receiver'):
   peer._qa_receiver.cancel();await asyncio.gather(peer._qa_receiver,return_exceptions=True)

async def main():
 faulthandler.dump_traceback_later(15,repeat=True)
 def stage(value):
  row=dict(stage=value,time=time.monotonic());save(attempt/'preparation-stage.json',row)
  with (attempt/'preparation-stages.jsonl').open('a',encoding='utf8')as f:f.write(json.dumps(row)+'\n')
 stage('verifying1604sourcefiles')
 pins=json.loads((HERE/'server-source-pins.json').read_bytes())
 assert len(pins)==binding['source_pin_count']==1604
 for name,digest in pins.items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
 private=attempt/'private';private.mkdir(exist_ok=False);create(private,'127.0.0.1')
 stage('constructing_application')
 cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=192,
  state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
  tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=attempt/'server-logs')
 app=Application(cfg);server=None;peers=[];values=[];errors=[];observed=[];status={};entered=None;returned=None;entry_towns=[]
 original_handle=FriendsSession.handle
 def track(s,event,*args,**kwargs):
  if values and s.account.uid==values[-1]['uid'] and event.kind in(0x28,0x88b,0x417,0x225,0x227):
   row=dict(kind=event.kind,bytes=len(event.payload),phase=s.phase,time=time.monotonic())
   if event.kind==0x225:row['requested_town']=struct.unpack_from('>i',event.payload)[0]
   if event.kind==0x88b:
    with closing(sqlite3.connect(cfg.state_file))as db:entry_towns[:]=db.execute('SELECT uid,town FROM location ORDER BY uid').fetchall()
    row['actual_source_town']=dict(entry_towns)[s.account.uid]
    save(attempt/'actual-entry-towns.json',dict(native_uid=s.account.uid,towns=entry_towns))
   observed.append(row)
  return original_handle(s,event,*args,**kwargs)
 try:
  stage('starting_application')
  await app.start()
  stage('creating32privatecharacters')
  for i in range(32):
   identity=app.registry.create('ownedweddingnative'+str(i))
   name='OwnHall'+str(i);uid=Characters(cfg.state_file,identity['id']).create(name,2 if i==1 else 1,'owned-wedding-native:'+str(i))['uid']
   LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
   values.append(dict(identity=identity,account_id=identity['id'],uid=uid,character_name=name))
  uid=[v['uid']for v in values];aid=[v['account_id']for v in values];now=int(time.time())
  def guard(db):assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid[0],)).fetchone()==(aid[0],)
  with closing(sqlite3.connect(cfg.state_file))as db,db:
   grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1)],uid[0])
   db.execute('UPDATE reward_balances SET ed=500 WHERE uid=?',(uid[0],))
   relationships.propose(db,uid[0],aid[0],uid[1],aid[1],'owned-groom','owned-bride',rel.descriptor(values[1]['character_name']),
    'owned-native-wedding-proposal',guard=guard,encode=lambda *args:[],now=now-60)
   body=struct.pack('>bQ',0,uid[0])+wstring(values[0]['character_name'])+struct.pack('>QBH',0,0,0)+struct.pack('>Q',uid[1])+wstring(values[1]['character_name'])+bytes(1)+rel.descriptor(values[1]['character_name'])
   relationships.answer(db,uid[1],aid[1],uid[0],aid[0],'owned-bride','owned-groom',body,
    'owned-native-wedding-acceptance',guard=guard,encode=lambda *args:[],now=now-60)
  FriendsSession.handle=track;Peer.until=until;Peer.close=close
  server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('worker_error','notification_error','connection_task_error')else None)
  _,port=await server.start();cert=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
  for v in values:
   identity=v['identity'];v['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=cert)
  for i,v in enumerate(values[:31]):
   stage('authenticating_protocol_actor'+str(i));await connect(v,peers)
  def read(sql,args=()):
   with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
  groom,bride=peers[:2]
  await groom.query(0x80d,struct.pack('>i',1))
  assert (await groom.query(0x80f,struct.pack('>IIH',1,1200277142,1))).payload[:4]==bytes(4)
  ring=read('SELECT uid FROM inventory_items WHERE owner=?AND template=277142',(uid[0],))[0][0]
  ends=(now//3600)*3600+86340  # Current real calendar hour, already open; no clock patch.
  raw=struct.pack('>bbQQQB',5,4,ends,uid[1],ring,1)+wstring('Owned32 native scene')+wstring('')+struct.pack('>bI',0,0)
  assert (await groom.query(0x887,raw)).payload[:4]==bytes(4)
  tickets={}
  for i in range(2):
   ids=[r[0]for r in read('SELECT mail_id FROM native_relationship_mail WHERE reservation=1 AND recipient_uid=?ORDER BY mail_id',(uid[i],))]
   assert ids
   claim=struct.pack('>I',len(ids))+b''.join(struct.pack('>Q',j)for j in ids)+bytes(6)
   assert (await peers[i].query(0x1d4,claim)).payload[:4]==bytes(4)
   tickets[i]=read('SELECT uid FROM inventory_items WHERE owner=?AND template=277151',(uid[i],))[0][0]
  for i,p in enumerate(peers):
   stage('admitting_protocol_actor'+str(i))
   body=struct.pack('>bQiB',2 if i<2 else 3,tickets.get(i,0),1,0)+wstring('')
   assert (await p.query(0x88b,body,reply=0x415)).payload[:4]==bytes(4),i
  room=app.world.weddings.room(app.playing[aid[0]]);assert len(room.members)==31
  baseline=read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')
  inventory=read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')
  save(private/'bridge.json',values[-1]['bridge'])
  save(attempt/'server-ready.json',dict(uid=uid[-1],account=aid[-1],family=1,guild_case=False,reservation=1,
   world=903,protocol31_ready=True,real_calendar_no_clock_patch=True,
   slots=[dict(uid=u,role=1 if i==0 else 2 if i==1 else 4)for i,u in enumerate(uid)],
   production_database_access=False,source_pins_sha256=binding['source_pins_sha256'],
   minimum_scene_seconds=2 if json.loads((attempt/'preparation.json').read_bytes())['town_return_only']else 120))
  faulthandler.cancel_dump_traceback_later()
  began=time.monotonic()
  while not(attempt/'server.stop').exists()and time.monotonic()-began<300:
   s=app.playing.get(aid[-1]);phase=None if s is None else s.phase
   if s is not None and app.world.weddings.room(s)is room:
    assert len(room.members)==32
    if entered is None:entered=time.monotonic()
   if entered is not None and phase=='town_ready'and app.world.weddings.room(s)is None:
    if returned is None:returned=time.monotonic()
   status=dict(protocol31_ready=True,phase=phase,members=len(room.members),
    native_joined=entered is not None,native_returned=returned is not None,
    native_hall_seconds=None if entered is None else (returned or time.monotonic())-entered,
    events=observed,errors=errors,observed_seconds=time.monotonic()-began)
   save(attempt/'status.json',status)
   if returned is not None and time.monotonic()-returned>2:
    assert read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')==baseline
    assert read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')==inventory
    assert entry_towns and read('SELECT uid,town FROM location ORDER BY uid')==entry_towns
    save(attempt/'scenario-complete.json',dict(ok=not errors,**status));break
   await asyncio.sleep(.25)
  save(attempt/'server-result.json',dict(ok=returned is not None and not errors,**status,
   natural_GUI=False,client_transport_signed=True,candidate_server_installed=False))
 except BaseException:
  save(attempt/'server-failure.json',dict(error=traceback.format_exc()));raise
 finally:
  FriendsSession.handle=original_handle
  for peer in reversed(peers):await peer.close()
  Peer.close=original_close
  if server is not None:await server.close()
  app.close()
if __name__=='__main__':asyncio.run(main())
