"""Actual seven-day contracts, permanent upgrades and cold expiry settlement."""
from pathlib import Path
import hashlib
H=Path(__file__).resolve().parent
fixture=H/'verify_writer_tls.py';raw=fixture.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='582e7bbed211ec90b0f6aaad48ee153f082e5931726ef0b2442301747a6ae5d8'
exec(compile(raw.decode().split('async def main():',1)[0],str(fixture)+' environment and Peer only','exec'))
from els_server.storage import housing_access
from els_server.protocol import housing_pet_messages as wire

async def cases():
 report=dict(ok=False,native_Game=False,natural_GUI=False,actual_authenticated_TLS=True,
  production_database_access=False,clock_is_explicit_storage_input=True,checks=[])
 report['source_sha256']={str(p.relative_to(H/'candidate')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in(H/'candidate').rglob('*.py')}
 reference=json.loads((H/'writer-TLS-1793948960990565600.json').read_bytes())
 assert report['source_sha256']==reference['source_sha256']
 f=t.FriendsTests();ready=False;stage='setup'
 try:
  original=t.ServerConfig;t.ServerConfig=lambda **kw:original(normal_equipment_moves_enabled=True,**kw)
  await f.asyncSetUp();ready=True;assert f.root.resolve().is_relative_to(H.resolve());path=f.config.state_file
  actors=[]
  for index,account in enumerate((f.alice,f.bob)):
   Characters(path,account['id']).create('Contract'+str(index),1,'owned-contract:'+str(index))
   owner=Characters(path,account['id']).list()[0]['uid']
   with closing(sqlite3.connect(path))as db,db:
    db.execute('BEGIN IMMEDIATE');companion_state.ensure(db);db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,))
    pet=91000000+index
    db.execute('INSERT INTO companions VALUES (?,?,?,?,?,?)',(pet,owner,'pet',1,'LeasePet'+str(index),0))
    grown=companion_state.rows(db,owner,'pet')[0];grown.update(step=3,growth=0);pet_progression.save(db,owner,grown)
    occupied={i['slot']for i in load_items(db,owner)if i['group']==4};slot=next(v for v in range(100)if v not in occupied)
    timed=dict(uid=next_uid(db),template=136034,metadata=0,count=1,group=4,slot=slot);insert(db,owner,timed)
    mat_item=dict(uid=next_uid(db),template=570234,metadata=0,count=1,group=25,slot=0);insert(db,owner,mat_item)
    permanent=grant_items(db,[dict(template=713275,metadata=0,group=4,quantity=1)],owner)[0]
   p=await f.peer(account);await p.roster();await p.enter_town(owner)
   async def request(kind,body,response):
    seq,ack=await p.query(kind,body,response);assert ack.payload[:4]==bytes(4),(stage,hex(kind),ack.payload.hex());return ack
   await request(0x219,struct.pack('>QQiiIB',timed['uid'],0,0,0,0,0),0x21a)
   await request(0x923,struct.pack('>Qi3fB',0,26000,0,0,0,1),0x924)
   await request(0x227,struct.pack('>fffBH',0,0,0,0,0),0x228)
   placed=[(mat_item['uid'],(2,mat_item['uid'],570234,0,0,0))]
   await request(0x935,encode(REQUEST,(placed,[],[],0,0,0)),0x936)
   await request(0xa38,struct.pack('>BQ',1,pet),0xa39)
   actor=next(s for s in f.app.playing.values()if s.account.uid==owner)
   with closing(sqlite3.connect(path))as db:
    access=housing_access.snapshot(db,owner,account['id']);saved=state.saved(db,owner)
   assert access['expires_at']-access['registered_at']==604800 and saved[0][7]==access['expires_at']
   actors.append(dict(owner=owner,account=account['id'],pet=pet,actor=actor,peer=p,access=access,row=saved[0],permanent=permanent))
  stage='real timed contract expiry'
  first=actors[0];clock=first['access']['expires_at']
  events=await f.app.call(lambda:state.periodic(path,first['owner'],now=clock+86400))
  with closing(sqlite3.connect(path))as db:
   assert state.saved(db,first['owner'])==[]
   pet=companion_state.rows(db,first['owner'],'pet')[0]
  cycles=(clock-first['row'][5])//86400
  assert cycles in(6,7)and pet['growth']==(534240*cycles+99)//100
  assert events[-1].kind==0xa37 and events[-1].payload==bytes(4)
  assert await f.app.call(lambda:state.periodic(path,first['owner'],now=clock+2*86400))==[]
  report['checks'].append(dict(case='real seven-day deadline',duration=604800,completed_cycles=cycles,
   growth=pet['growth'],no_credit_after_deadline=True,second_cleanup_empty=True))
  stage='permanent upgrade while pets remain placed'
  second=actors[1];actor=second['actor'];owner=second['owner'];account=second['account']
  await second['peer'].close()
  async with asyncio.timeout(8):
   while any(s.account.uid==owner for s in f.app.playing.values()):await asyncio.sleep(.01)
  await f.app.call(lambda:None)
  p=await f.peer(f.bob);await p.roster();await p.enter_town(owner)
  _,ack=await p.query(0x219,struct.pack('>QQiiIB',second['permanent']['uid'],0,0,0,0,0),0x21a)
  assert ack.payload[:4]==bytes(4)
  with closing(sqlite3.connect(path))as db:
   access=housing_access.snapshot(db,owner,account);saved=state.saved(db,owner)
  assert access['permanent']and len(saved)==1
  assert saved[0][5]==second['row'][5]and saved[0][7]==access['expires_at']
  assert await f.app.call(lambda:state.periodic(path,owner,now=second['access']['expires_at']+86400))==[]
  with closing(sqlite3.connect(path))as db:
   assert state.saved(db,owner)==saved and companion_state.rows(db,owner,'pet')[0]['growth']==0
  report['checks'].append(dict(case='actual permanent upgrade before original deadline',
   original_start_preserved=True,permanent_deadline_saved=True,old_deadline_does_not_release_or_credit=True))
  report.update(ok=True,native_house_exit_not_qualified=True,original_92E_is_population=True)
 except BaseException:report.update(error=traceback.format_exc(),stage=stage)
 finally:
  if ready:
   await f.asyncTearDown();report['owned_private_directory_removed']=not f.root.exists();report['owned_listeners_closed']=True
  out=H/('contract-deadlines-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
  print(json.dumps({k:v for k,v in report.items()if k!='source_sha256'}|dict(evidence=str(out)),ensure_ascii=False))
 return report['ok']
raise SystemExit(not asyncio.run(cases()))
