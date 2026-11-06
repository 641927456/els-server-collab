"""Owned authenticated TLS lifecycle plus explicit-clock settlement/replay checks."""
from pathlib import Path
from contextlib import closing
import ast,asyncio,ctypes,hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,time,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent;B=H.parent/'transport-routing-variants-v1/full-source-v1'
sys.dont_write_bytecode=True
ctypes.WinDLL(str(H.parent/'duel-wire-v2/full-source/python/sqlite3.dll'))
sys.path[:0]=[str(B),str(R/'tools/pylibs'),str(R/'tools'),str(R)]
import els_server,els_server.domain,els_server.storage,els_server.protocol
for pkg,name in((els_server.domain,'domain'),(els_server.storage,'storage'),(els_server.protocol,'protocol')):
 pkg.__path__.insert(0,str(H/'candidate/els_server'/name))
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame,decode_event,decode_frame
from els_server.protocol.housing_layout_messages import REQUEST,encode
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.item_instances import next_uid,insert
from els_server.storage.characters import Characters
from els_server.storage import housing_pets as state,companion_state,pet_progression
from els_server.domain.housing_layout_flow import handle as room_action
spec=importlib.util.spec_from_file_location('owned_housing_tls_fixture',R/'tests/test_friends_server.py');t=importlib.util.module_from_spec(spec);sys.modules[spec.name]=t;spec.loader.exec_module(t)
tempfile.tempdir=str(H)

class Peer(t.Peer):
 async def enter_town(self,uid,town=20000):
  # Current original5BF carries two zero cursors. The generic root test Peer
  # still sends an empty body; reuse the already qualified guild login body.
  for kind,response,payload in((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uid)),
   (0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),
   (0x225,0x226,struct.pack('>iB',town,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
   await self.send(kind,payload);await self.until(response)
 async def send(self,kind,payload=b'',event_id=0x202):
  self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing))
  self.outgoing+=1;await self.writer.drain()
 async def until(self,kind):
  async with asyncio.timeout(12):
   for _ in range(240):
    frame=decode_frame(await t.read_wire(self.reader),self.keys,expected_sequence=self.incoming);self.incoming+=1
    event=decode_event(frame.plaintext)
    if event.kind==kind:return event
  raise AssertionError('Missing original response '+hex(kind))
 async def query(self,kind,payload,response):
  sequence=self.outgoing;await self.send(kind,payload);answer=await self.until(response)
  await self.send(0x48d);await self.until(0x48f);return sequence,answer
t.Peer=Peer

async def main():
 report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,
  production_database_access=False,original_EXE_KOM_modified=False,checks=[],packets=[],
  synthetic_owned_pet_fixtures=True,elapsed_time_for_settlement_is_explicit_storage_clock=True)
 f=t.FriendsTests();ready=False;stage='setup'
 original_config=t.ServerConfig;t.ServerConfig=lambda **kw:original_config(normal_equipment_moves_enabled=True,**kw)
 source_pins={str(p.relative_to(H/'candidate')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in(H/'candidate').rglob('*.py')}
 report['source_sha256']=source_pins
 report['tester_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 try:
  await f.asyncSetUp();ready=True;assert f.root.resolve().is_relative_to(H.resolve())
  path=f.config.state_file
  for account in(f.alice,f.bob):
   roster=Characters(path,account['id']);character=roster.create('House'+str(account['id']),1,'owned-housing:'+str(account['id']))
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE');companion_state.ensure(db)
   db.execute('UPDATE characters SET level=99')
   uids=[r[0]for r in db.execute('SELECT uid FROM characters ORDER BY uid')];owner,foreign=uids
   db.execute('UPDATE reward_balances SET ed=60000000 WHERE uid=?',(owner,))
   for i in range(1,7):
    uid=90000000+i;subject=foreign if i==6 else owner
    db.execute('INSERT INTO companions VALUES (?,?,?,?,?,?)',(uid,subject,'pet',1,'HomePet'+str(i),0))
   adult=next(p for p in companion_state.rows(db,owner,'pet')if p['uid']==90000004)
   adult.update(step=3,growth=0);pet_progression.save(db,owner,adult)
   contract=grant_items(db,[dict(template=713275,metadata=0,group=4,quantity=1)],owner)[0]
   large=dict(uid=next_uid(db),template=570286,metadata=0,count=1,group=25,slot=1)
   # Existing ownership fixture, distinct from a newly authorized DIY grant.
   insert(db,owner,large)
  peer=await f.peer(f.alice);await peer.roster();await peer.enter_town(owner)
  def live():return next(s for s in f.app.playing.values()if s.account.uid==owner)
  async def action(kind,body,reply,success=True):
   sequence,event=await peer.query(kind,body,reply)
   assert(struct.unpack_from('>i',event.payload)[0]==0)is success,(stage,hex(kind),event.payload.hex())
   report['packets'].append(dict(kind=reply,payload_hex=event.payload.hex()))
   return sequence,event
  def sql(query,values=()):
   with closing(sqlite3.connect(path))as db:return db.execute(query,values).fetchall()
  def pets():
   with closing(sqlite3.connect(path))as db:return companion_state.rows(db,owner,'pet')
  def growth(uid):return next(p['growth']for p in pets()if p['uid']==uid)
  def placements():
   with closing(sqlite3.connect(path))as db:return state.saved(db,owner)
  def items():
   with closing(sqlite3.connect(path))as db:return load_items(db,owner)
  async def layout(item):
   rows=[]if item is None else[(item['uid'],(2,item['uid'],item['template'],0,0,0))]
   return await action(0x935,encode(REQUEST,(rows,[],[],0,0,0)),0x936)
  async def enter_house():
   await action(0x923,struct.pack('>Qi3fB',0,26000,0,0,0,1),0x924)
   await action(0x227,struct.pack('>fffBH',0,0,0,0,0),0x228)
  stage='buy original small mat'
  await action(0xea,struct.pack('>BHIiii',0,0,1,570234,1,10018),0xeb)
  small=next(i for i in items()if i['template']==570234)
  assert sql('SELECT ed FROM reward_balances WHERE uid=?',(owner,))==[(30000000,)]
  report['checks'].append('Original EA purchase at Ariel10018 deducts exactly30000000 ED and creates one bag25 singleton')
  stage='contract and one-slot mat'
  await action(0x219,struct.pack('>QQiiIB',contract['uid'],0,0,0,0,0),0x21a)
  await enter_house()
  before_schema=sql("SELECT name FROM sqlite_master WHERE name='character_housing_layouts_v1'")
  floating=[(small['uid'],(small['uid'],small['template'],2,(0.,0.,0.),0))]
  await action(0x935,encode(REQUEST,([],floating,[],0,0,0)),0x936,False)
  assert sql("SELECT name FROM sqlite_master WHERE name='character_housing_layouts_v1'")==before_schema
  report['checks'].append('Actual TLS rejects free-position pet mat before saving a nonprojecting layout')
  await layout(small)
  before_items=items();before_balances=sql('SELECT ed,experience FROM reward_balances WHERE uid=?',(owner,))
  stage='normal place and replay'
  payload=struct.pack('>BQ',1,90000001);sequence,_=await action(0xa38,payload,0xa39)
  before=placements();assert len(before)==1 and before[0][2]==90000001
  with closing(sqlite3.connect(path))as db:
   from els_server.storage.pet_support import owned_pet
   assert owned_pet(db,owner,90000001)['uid']==90000001
  report['checks'].append('Housing does not add an unverified global restriction to ordinary owned-pet support; summon and expedition keep explicit housing exclusion')
  event=Event(0x202,kind=0xa38,payload=payload,performers=(0,))
  replay=await f.app.call(lambda:room_action(live(),event,sequence))
  assert replay[-1].payload[:4]==bytes(4)and placements()==before
  await action(0xa38,payload,0xa39,False)
  await action(0xa38,struct.pack('>BQ',2,90000002),0xa39,False)
  await action(0xa38,struct.pack('>BQ',1,90000006),0xa39,False)
  assert placements()==before and items()==before_items
  stage='mat removal guard'
  await action(0x935,encode(REQUEST,([],[],[],0,0,0)),0x936,False)
  assert placements()==before
  report['checks'].append('TLS place, actual guarded-handler replay, duplicate/overflow/foreign rejection and removing an occupied mat preserve state and items')
  stage='cold reconnect and entry'
  await peer.close()
  async with asyncio.timeout(8):
   while any(s.account.uid==owner for s in f.app.playing.values()):await asyncio.sleep(.01)
  await f.app.call(lambda:None)
  peer=await f.peer(f.alice);await peer.roster();await peer.enter_town(owner)
  assert placements()==before
  await enter_house()
  report['checks'].append('Reauthentication and original924 retain the placed UID, slot, original start time and mat; normal town remains the saved location')
  stage='early retrieve'
  await action(0xa3a,payload,0xa3b)
  assert placements()==[]and growth(90000001)==0
  await action(0xa38,struct.pack('>BQ',1,90000006),0xa39,False)
  assert placements()==[]
  stage='four-slot mat'
  await layout(large)
  for i in range(1,5):await action(0xa38,struct.pack('>BQ',i,90000000+i),0xa39)
  assert len(placements())==4
  await action(0xa38,struct.pack('>BQ',5,90000005),0xa39,False)
  report['checks'].append('Original A3A/A3B early retrieval grants no partial period; large mat admits exactly four pets')
  stage='settlement and rollback'
  actor=live();context=actor.housing_own_room;account=actor.account.account_id
  rows=placements();clock=max(r[5]for r in rows)+28800
  def guard(db):
   assert live()is actor and actor.housing_own_room is context and actor.phase=='housing_ready'
  def perform(uid,slot,op,at):
   return state.perform(path,owner,account,0xa3a,struct.pack('>BQ',slot,uid),op,context['generation'],context['operation'],guard,now=at)
  answer=await f.app.call(lambda:perform(90000001,1,'owned-completed-cycle',clock))
  assert answer[-1].payload[:4]==bytes(4)and growth(90000001)==382 and len(placements())==3
  replay=await f.app.call(lambda:perform(90000001,1,'owned-completed-cycle',clock+28800))
  assert growth(90000001)==382 and len(placements())==3
  snapshot=placements();before_growth=growth(90000002)
  def changed_guard(db):
   changed_guard.count+=1
   if changed_guard.count==2:raise ValueError('owned precommit actor switch')
  changed_guard.count=0
  try:
   await f.app.call(lambda:state.perform(path,owner,account,0xa3a,struct.pack('>BQ',2,90000002),'owned-rollback',context['generation'],context['operation'],changed_guard,now=clock))
  except ValueError as error:assert str(error)=='owned precommit actor switch'
  else:raise AssertionError('Precommit actor switch accepted')
  assert placements()==snapshot and growth(90000002)==before_growth
  report['checks'].append('Explicit completed8h writer credits382 points for original38160 baby-stage threshold; later replay credits none; a precommit actor switch rolls back both affinity and removal')
  stage='deadline expiry and renewal'
  # Short finite deadline fixtures stand for already saved timed contracts;
  # the actual contract and original seven-day duration are unchanged.
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE')
   db.execute('UPDATE character_housing_pets_v1 SET deadline=? WHERE owner=?',(clock,owner))
  expired=await f.app.call(lambda:state.periodic(path,owner,now=clock+99999))
  assert expired and placements()==[]
  assert [growth(90000000+i)for i in range(1,5)]==[382,382,382,5343]
  assert await f.app.call(lambda:state.periodic(path,owner,now=clock+199999))==[]
  assert items()==before_items and sql('SELECT ed,experience FROM reward_balances WHERE uid=?',(owner,))==before_balances
  report['checks'].append('Expired saved placements settle only through the deadline, release all slots once and preserve ED/XP/inventory')
  stage='shared summon replay'
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE');db.execute('UPDATE companion_active SET pet=0 WHERE owner=?',(owner,))
  original=companion_state.handle(path,owner,0x2ec,struct.pack('>Q',90000001),'owned-old-summon',account_id=account)
  companion_state.handle(path,owner,0x2ec,bytes(8),'owned-later-unsummon',account_id=account)
  restored=companion_state.handle(path,owner,0x2ec,struct.pack('>Q',90000001),'owned-old-summon',account_id=account)
  assert int.from_bytes(original.payload[4:12],'big')==90000001 and restored.payload[4:12]==bytes(8)
  await action(0xa38,payload,0xa39)
  try:companion_state.handle(path,owner,0x2ec,struct.pack('>Q',90000001),'owned-old-summon',account_id=account)
  except ValueError as error:assert 'placed in housing'in str(error)
  else:raise AssertionError('Old summon restored a housed pet')
  await action(0xa3a,payload,0xa3b)
  report['checks'].append('Replayed old summon returns the current unsummoned state; replay against a newly housed pet is rejected without changing the active UID')
  stage='loaded sources'
  for relative,sha in source_pins.items():
   module=__import__(relative[:-3].replace('/','.'),fromlist=['*']);actual=Path(module.__file__)
   assert actual.resolve()==(H/'candidate'/relative).resolve()and hashlib.sha256(actual.read_bytes()).hexdigest()==sha
  report.update(ok=True,source_sha256=source_pins,fixture_sha256=hashlib.sha256((R/'tests/test_friends_server.py').read_bytes()).hexdigest())
 except BaseException:
  report.update(error=traceback.format_exc(),stage=stage)
  if ready:report['server_errors']=[e for e in f.events if 'error'in str(e.get('event','')).lower()]
 finally:
  if ready:
   await f.asyncTearDown();report['owned_private_directory_removed']=not f.root.exists()
   report['owned_listeners_closed']=True
  out=H/('writer-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
  print(json.dumps({k:v for k,v in report.items()if k not in('packets','source_sha256')}|dict(evidence=str(out)),ensure_ascii=False),flush=True)
 return report['ok']
raise SystemExit(not asyncio.run(main()))
