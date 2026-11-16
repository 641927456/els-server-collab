"""Actual92E room population, SQL profile authority and durable admission checks."""
from pathlib import Path
import hashlib
H=Path(__file__).resolve().parent
p=H/'verify_writer_tls.py';raw=p.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='d2353cd877eac174a0591eae2131e3b1f6cc8e08fd76bf5ee075ea3989322018'
exec(compile(raw.decode().split('async def main():',1)[0],str(p)+' environment and Peer only','exec'))
from els_server.domain.housing_room_flow import handle as room_handle
from unittest.mock import patch

async def main():
 report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,
  production_database_access=False,checks=[],packets=[])
 report['source_sha256']={str(p.relative_to(H/'candidate')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in(H/'candidate').rglob('*.py')}
 f=t.FriendsTests();ready=False;stage='setup'
 try:
  original=t.ServerConfig;t.ServerConfig=lambda **kw:original(normal_equipment_moves_enabled=True,**kw)
  await f.asyncSetUp();ready=True;assert f.root.resolve().is_relative_to(H.resolve());path=f.config.state_file
  Characters(path,f.alice['id']).create('HomeOwner',1,'owned-population')
  owner=Characters(path,f.alice['id']).list()[0]['uid']
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,))
   contract=grant_items(db,[dict(template=713275,metadata=0,group=4,quantity=1)],owner)[0]
  peer=await f.peer(f.alice);await peer.roster();await peer.enter_town(owner)
  async def request(kind,payload,reply,ok=True):
   sequence,event=await peer.query(kind,payload,reply)
   assert(event.payload[:4]==bytes(4))is ok,(stage,kind,event.payload.hex())
   report['packets'].append(dict(kind=reply,payload_hex=event.payload.hex()));return sequence,event
  await request(0x219,struct.pack('>QQiiIB',contract['uid'],0,0,0,0,0),0x21a)
  await request(0x923,struct.pack('>Qi3fB',0,26000,0,0,0,1),0x924)
  actor=next(s for s in f.app.playing.values()if s.account.uid==owner)
  before_sql=None
  def saved():
   with closing(sqlite3.connect(path))as db:
    return(db.execute('SELECT town,x,y,z FROM location WHERE uid=?',(owner,)).fetchall(),
     db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(owner,)).fetchall(),load_items(db,owner))
  before_sql=saved();stage='original92E before invented town readiness'
  # This original request follows923 directly; no fabricated227 is needed.
  sequence,event=await request(0x92e,struct.pack('>fff',12.5,20.0,-7.0),0x92f)
  assert struct.unpack_from('>I',event.payload,4)[0]==1
  assert int.from_bytes(event.payload[16:24],'big')==owner
  assert 'HomeOwner'.encode('utf-16le')in event.payload
  assert actor.phase=='housing_ready'and saved()==before_sql
  report['checks'].append('Actual original92E after923 returns one actual self record and preserves saved town, ED, XP and inventory')
  stage='SQL rather than stale display cache'
  def stale_cache():
   with patch.object(actor.account,'character',return_value=dict(uid=owner,name='STALE DISPLAY',unit_type=1,unit_class=1,level=1)):
    return room_handle(actor,Event(0x202,kind=0x92e,payload=struct.pack('>fff',12.5,20.,-7.),performers=(0,)),sequence+500)
  replies=await f.app.call(stale_cache)
  assert len(replies)==1 and replies[0].payload==event.payload
  report['checks'].append('A deliberately stale account display cache cannot change the SQL-owned name, class or level')
  stage='malformed position and durable generation'
  await request(0x92e,bytes(11),0x92f,False)
  await request(0x92e,struct.pack('>fff',float('nan'),0.,0.),0x92f,False)
  original_context=actor.housing_own_room
  def stale_admission():
   actor.housing_own_room={**original_context,'generation':original_context['generation']+1}
   try:return room_handle(actor,Event(0x202,kind=0x92e,payload=bytes(12),performers=(0,)),sequence+501)
   finally:actor.housing_own_room=original_context
  bad=await f.app.call(stale_admission)
  assert len(bad)==1 and struct.unpack_from('>i',bad[0].payload)[0]==-1 and saved()==before_sql
  report['checks'].append('Wrong length, nonfinite position and replaced durable admission return native failure without database changes')
  assert report['source_sha256']=={str(p.relative_to(H/'candidate')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in(H/'candidate').rglob('*.py')}
  report.update(ok=True,owner=owner)
 except BaseException:report.update(error=traceback.format_exc(),stage=stage)
 finally:
  if ready:
   await f.asyncTearDown();report['owned_private_directory_removed']=not f.root.exists();report['owned_listeners_closed']=True
  out=H/('population-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
  print(json.dumps({k:v for k,v in report.items()if k not in('packets','source_sha256')}|dict(evidence=str(out)),ensure_ascii=False))
 return report['ok']
raise SystemExit(not asyncio.run(main()))
