from pathlib import Path
from contextlib import closing
import ast,asyncio,hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,traceback,uuid
from unittest.mock import patch
W=Path(__file__).resolve().parent;R=Path('G:/els');manifest=json.loads((W/'candidate-manifest.json').read_bytes());channel='local'if'--local'in sys.argv else'online';binding=next(x for x in manifest['channels']if x['channel']==channel);runtime=Path(binding['runtime']);fixed='--fixed'in sys.argv
sys.dont_write_bytecode=True;sys.path[:0]=[str(runtime),str(R/'tools')];tempfile.tempdir=str(W)
from els_server.domain import native_line_triggers as triggers
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.town_travel import catalog as towns
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.storage.characters import Characters
from els_server.storage.seal_quests import QuestState
assert hashlib.sha256(Path(triggers.__file__).read_bytes()).hexdigest()==binding['reader_sha256']
os.environ['ELS_TEST_CERT_DIR']=str(R/'analysis/luciel-natural-dynamic-passive-01a1531c-20261020-v1/party-UI-r10/tls')
spec=importlib.util.spec_from_file_location('sky_owned_peer',R/'tests/test_friends_server.py');t=importlib.util.module_from_spec(spec);sys.modules[spec.name]=t;spec.loader.exec_module(t)
prior=R/'analysis/monster-economy-formal-20261025-v1/verify_native.py';nodes=[n for n in ast.parse(prior.read_text('utf8')).body if isinstance(n,ast.ClassDef)and n.name=='Peer'];exec(compile(ast.Module(body=nodes,type_ignores=[]),str(prior),'exec'))
class TriggerPeer(Peer):
 async def send(self,kind,payload=b'',event_id=0x202):
  if kind!=0x30a:return await super().send(kind,payload,event_id)
  event=Event(event_id,kind=kind,payload=payload,performers=(0,))
  self.writer.write(encode_frame(encode_event(event),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
t.Peer=TriggerPeer
if fixed:triggers.__file__=str(W/'candidate'/channel/'els_server/domain/native_line_triggers.py')
triggers.definitions.cache_clear()
async def main():
 c=t.FriendsTests();await c.asyncSetUp();out=dict(ok=False,channel=channel,fixed=fixed,natural_GUI=False,production_writes=False,original_reader_code=True,actual_Application_TLS=True,controlled_owned_checkpoint=True)
 try:
  uid=Characters(c.config.state_file,c.alice['id']).create('SkyProbe',7,'sky-probe')['uid'];QuestState(c.config.state_file,uid,account_id=c.alice['id']).snapshot()
  with closing(sqlite3.connect(c.config.state_file))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
  peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid);s=c.app.playing[c.alice['id']]
  run=DungeonRun(33872,str(uuid.uuid4()))
  def checkpoint(stage,part):
   run._load_stage(stage);run.stage=stage;run.part=part;run.visits+=1
   s.dungeon_run=run;s.phase='dungeon_active';s.dungeon_substage_synced=True;s.clear_notified=False;s.part_end_notified=False;s.dungeon_failed=False;s.dungeon_participants=frozenset((uid,))
  await c.app.call(checkpoint,0,1)
  before=s.account.get_inventory_snapshot();deaths=dict(run.defeated)
  rows=json.loads((W/'new-rules.json').read_bytes());passed=[]
  for number,row in enumerate(rows if fixed else rows[:1]):
   await c.app.call(checkpoint,row['stage'],row['part'])
   payload=struct.pack('>i',row['trigger']);await peer.send(0x30a,payload);ack=await peer.until(0x30b)
   assert ack.payload==(bytes(4)if fixed else struct.pack('>i',-1)),(row,ack.payload)
   if fixed:
    notice=await peer.until(0x30c);assert notice.payload==payload
    event=Event(0x202,kind=0x30a,payload=payload,performers=(0,))
    duplicate=await c.app.call(triggers.handle,s,event)
    assert[(e.kind,e.payload)for e in duplicate]==[(0x30b,bytes(4))]
   passed.append((row['stage'],row['part'],row['trigger']))
  if fixed:
   await c.app.call(checkpoint,1,0);event=Event(0x202,kind=0x30a,payload=bytes(4),performers=(0,));denied=[]
   def refusal(label,ev=event):
    result=triggers.handle(s,ev);assert[(x.kind,x.payload)for x in result]==[(0x30b,struct.pack('>i',-1))],label;denied.append(label)
   refusal('unknown trigger',Event(0x202,kind=0x30a,payload=struct.pack('>i',100),performers=(0,)))
   refusal('invalid payload',Event(0x202,kind=0x30a,payload=b'',performers=(0,)))
   refusal('wrong performer',Event(0x202,kind=0x30a,payload=bytes(4),performers=(uid,)))
   for name,value in (('dungeon_substage_synced',False),('clear_notified',True),('dungeon_failed',True),('dungeon_participants',frozenset((uid,uid+1)))):
    old=getattr(s,name);setattr(s,name,value)
    try:refusal(name)
    finally:setattr(s,name,old)
   held=c.app.playing.pop(c.alice['id'])
   try:refusal('stale lease')
   finally:c.app.playing[c.alice['id']]=held
   original=run.graph;run.graph=dict(original,source_sha256='0'*64)
   try:refusal('changed resource')
   finally:run.graph=original
   old=run.part;run.part=1
   try:refusal('wrong room')
   finally:run.part=old
   old=run.current['npcs'];run.current['npcs']=[n for n in old if n['template']!=2266]
   try:refusal('missing original actor')
   finally:run.current['npcs']=old
   out['denials']=denied
  assert s.account.get_inventory_snapshot()==before and run.defeated==deaths
  out.update(ok=True,cases=passed,existing_rules_preserved=126,duplicate_ACK_only=fixed,inventory_and_defeated_unchanged=True)
 except Exception as e:out.update(error=repr(e),traceback=traceback.format_exc(limit=8),server_errors=[{k:v for k,v in e.items()if k in('event','error')}for e in c.events if e['event']in('worker_error','protocol_error','connection_error')][-3:])
 finally:await c.asyncTearDown()
 (W/(channel+'-'+('candidate'if fixed else'baseline')+'-tests.json')).write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out));assert out['ok']
asyncio.run(main())
