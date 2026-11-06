from pathlib import Path
import ast,asyncio,hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,traceback,uuid
from contextlib import closing
R=Path('G:/els');W=Path(__file__).resolve().parent;A=W.parent;manifest=json.loads((W/'candidate-manifest.json').read_bytes());channel='local'if'--local'in sys.argv else'online';binding=next(r for r in manifest['channels']if r['channel']==channel);runtime=Path(binding['runtime']);sys.dont_write_bytecode=True;sys.path[:0]=[str(runtime),str(R/'tools')];tempfile.tempdir=str(W)
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain import native_line_triggers as triggers
from els_server.domain.town_travel import catalog as towns
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.storage.characters import Characters
from els_server.storage.seal_quests import QuestState
reader=Path(triggers.__file__);assert hashlib.sha256(reader.read_bytes()).hexdigest()==binding['reader_sha256'];triggers.__file__=str(W/'candidate'/channel/'els_server/domain/native_line_triggers.py');triggers.definitions.cache_clear()
os.environ['ELS_TEST_CERT_DIR']=str(R/'analysis/luciel-natural-dynamic-passive-01a1531c-20261020-v1/party-UI-r10/tls')
spec=importlib.util.spec_from_file_location('variant_fixed_peer',R/'tests/test_friends_server.py');t=importlib.util.module_from_spec(spec);sys.modules[spec.name]=t;spec.loader.exec_module(t)
p=R/'analysis/monster-economy-formal-20261025-v1/verify_native.py';nodes=[n for n in ast.parse(p.read_text('utf8')).body if isinstance(n,ast.ClassDef)and n.name=='Peer'];exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'))
class TriggerPeer(Peer):
 async def send(self,kind,payload=b'',event_id=0x202):
  if kind!=0x30a:return await super().send(kind,payload,event_id)
  event=Event(event_id,kind=kind,payload=payload,performers=(0,));self.writer.write(encode_frame(encode_event(event),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
t.Peer=TriggerPeer
rules=json.loads((W/'new-rules.json').read_bytes());assert len(rules)==11
async def main():
 c=t.FriendsTests();await c.asyncSetUp();out=dict(ok=False,channel=channel,actual_Application_TLS=True,controlled_owned_checkpoint=True,production_writes=False,natural_GUI=False,reader_source_unchanged=True,candidate_sha256=binding['sha256'])
 try:
  uid=Characters(c.config.state_file,c.alice['id']).create('VariantFixed',7,'variant-fixed')['uid'];QuestState(c.config.state_file,uid,account_id=c.alice['id']).snapshot()
  with closing(sqlite3.connect(c.config.state_file))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
  peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid);s=c.app.playing[c.alice['id']];runs={};results=[]
  def checkpoint(mid,stage,part):
   if mid not in runs:runs[mid]=DungeonRun(mid,str(uuid.uuid4()))
   run=runs[mid];run._load_stage(stage);run.stage=stage;run.part=part;run.visits+=1
   s.dungeon_run=run;s.dungeon_id=mid;s.phase='dungeon_active';s.dungeon_substage_synced=True;s.clear_notified=False;s.part_end_notified=False;s.dungeon_failed=False;s.dungeon_participants=frozenset((uid,));return run
  for row in rules:
   key=(row['dungeon'],row['stage'],row['part'],row['trigger']);mid,stage,part,activation=key;run=await c.app.call(checkpoint,mid,stage,part)
   assert any(n['template']==row['npc_template']for n in run.current['npcs']),key
   frozen=s.account.get_inventory_snapshot();balance=s.account.get_reward_balances();location=s.account.get_location();dead=dict(run.defeated);room=(run.stage,run.part,run.visits);hp=[(n['key'],n['hp'])for n in run.current['npcs']]
   payload=struct.pack('>i',activation);await peer.send(0x30a,payload);ack=await peer.until(0x30b);notice=await peer.until(0x30c);assert ack.payload==bytes(4)and notice.payload==payload,key
   event=Event(0x202,kind=0x30a,payload=payload,performers=(0,));duplicate=await c.app.call(triggers.handle,s,event)
   expected=[(0x30b,bytes(4))]+([(0x30c,payload)]if row['native_loop']else[]);assert[(e.kind,e.payload)for e in duplicate]==expected,key
   if row['native_loop']:
    await peer.send(0x30a,payload);assert(await peer.until(0x30b)).payload==bytes(4);assert(await peer.until(0x30c)).payload==payload
   assert s.account.get_inventory_snapshot()==frozen and s.account.get_reward_balances()==balance and s.account.get_location()==location
   assert run.defeated==dead and(run.stage,run.part,run.visits)==room and[(n['key'],n['hp'])for n in run.current['npcs']]==hp
   results.append(dict(key=key,result=0,notification=activation,duplicate='ACK+notification'if row['native_loop']else'ACK only'))
  run=await c.app.call(checkpoint,33891,0,0);event=Event(0x202,kind=0x30a,payload=bytes(4),performers=(0,));denied=[]
  def refuse(label,ev=event):
   result=triggers.handle(s,ev);assert[(x.kind,x.payload)for x in result]==[(0x30b,struct.pack('>i',-1))],label;denied.append(label)
  def check_denials():
   refuse('unknown activation',Event(0x202,kind=0x30a,payload=struct.pack('>i',99),performers=(0,)))
   refuse('malformed payload',Event(0x202,kind=0x30a,payload=b'',performers=(0,)))
   refuse('foreign performer',Event(0x202,kind=0x30a,payload=bytes(4),performers=(uid,)))
   for name,value in(('dungeon_substage_synced',False),('clear_notified',True),('dungeon_failed',True),('phase','town_ready'),('dungeon_participants',frozenset((uid,uid+1)))):
    old=getattr(s,name);setattr(s,name,value)
    try:refuse(name)
    finally:setattr(s,name,old)
   held=c.app.playing.pop(c.alice['id'])
   try:refuse('stale lease')
   finally:c.app.playing[c.alice['id']]=held
   old=run.graph;run.graph=dict(old,source_sha256='0'*64)
   try:refuse('changed graph source')
   finally:run.graph=old
   old=run.part;run.part=1
   try:refuse('wrong room')
   finally:run.part=old
   old=run.current['npcs'];run.current['npcs']=[n for n in old if n['template']!=2370]
   try:refuse('missing original actor')
   finally:run.current['npcs']=old
  await c.app.call(check_denials)
  controls=[]
  for mid,stage,part,activation in((34320,1,1,0),(33881,2,2,0)):
   await c.app.call(checkpoint,mid,stage,part);payload=struct.pack('>i',activation);await peer.send(0x30a,payload);assert(await peer.until(0x30b)).payload==bytes(4);assert(await peer.until(0x30c)).payload==payload;controls.append((mid,stage,part,activation))
  out.update(ok=True,repaired=results,existing_controls=controls,denied=denied,inventory_currency_location_HP_and_defeated_unchanged=True,qualification='Actual native-header App/TLS under valid owner lease; original client AI conditions, timing and visual effects remain untested.')
 except Exception as e:out.update(error=repr(e),traceback=traceback.format_exc(limit=9))
 finally:await c.asyncTearDown()
 (W/(channel+'-tests.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),'utf8');print(json.dumps(out));assert out['ok']
asyncio.run(main())
