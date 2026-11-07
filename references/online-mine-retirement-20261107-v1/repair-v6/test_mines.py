"""Thirteen source-pinned mine retirements through actual owned V99 TLS."""
from pathlib import Path
import asyncio,copy,hashlib,importlib.abc,importlib.util,json,os,sqlite3,struct,sys,traceback
from contextlib import closing
H=Path(__file__).resolve().parent;W=H.parent;C=H/'candidate'
class Candidate(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  p=C/Path(*fullname.split('.')).with_suffix('.py')
  if p.is_file():return importlib.util.spec_from_file_location(fullname,p)
sys.meta_path.insert(0,Candidate());sys.argv=[__file__]
os.environ['ELS_CRASH_TEST_RUNTIME']='G:/els/releases/online/native-online-disconnect-repair-20261107-v1'
spec=importlib.util.spec_from_file_location('owned_mine_v99_setup',W/'reproduce_tutorial_late_death.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
from els_server.domain import scene_actor_retirements as flow,scene_retirement_sources as rules
from els_server.game_data import client_data
from els_server.storage.seal_quests import ensure
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame

def retirement(npc,uid):
 return(struct.pack('>iBQQ6fBf',npc['key'],255,2**64-1,2**64-1,*([0.]*6),1,npc['hp'])
     +bytes(4)+struct.pack('>IQB',1,uid,0)+bytes(8)+bytes(4)+bytes(8))

def economy(path,uid):
 with closing(sqlite3.connect(path))as db:
  db.execute('BEGIN');return(db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uid,)).fetchone(),db.execute('SELECT *FROM inventory_items WHERE owner=?ORDER BY uid',(uid,)).fetchall())

async def main():
 f=r.f.FriendsTests();await f.asyncSetUp();result=dict(ok=False,production_modified=False,actual_Application=True,actual_authenticated_TLS=True,natural_route=False,natural_GUI=False)
 try:
  uid=r.f.Characters(f.config.state_file,f.alice['id']).create('MineFixed',1,'owned-mine-fixed')['uid']
  with closing(sqlite3.connect(f.config.state_file))as db,db:
   db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid));ensure(db)
   db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,26650,1,'{}'))
  peer=await f.peer(f.alice);await peer.roster();await r.admit(peer,uid,30252);s=f.app.playing[f.alice['id']]
  observed=[];put=peer.pending.put_nowait
  def record(e):observed.append(e);put(e)
  peer.pending.put_nowait=record;cases=[]
  for stage,part in [(0,1),(1,0),(1,1),(2,0)]:
   def scene():
    run=s.dungeon_run;run._load_stage(stage);run.part=part;run.next=None;run.ready_at=None;run.loaded()
    s.gate_stage=stage;s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.part_end_notified=False;s.defeated_npcs=run.defeated
    return[n for n in run.current['npcs']if n['template']==241]
   actors=await f.app.call(scene)
   for npc in actors:
    before=economy(f.config.state_file,uid);mark=len(observed);body=retirement(npc,uid)
    await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4);await peer.until(0xaf)
    await peer.send(0x48d);await peer.until(0x48f)
    assert s.dungeon_run.defeated[npc['key']]==body and npc['active']is False
    assert economy(f.config.state_file,uid)==before
    notices=sum(isinstance(e,Event)and e.kind==0xaf for e in observed[mark:])
    await peer.send(0xad,body);assert(await peer.until(0xae)).payload==bytes(4)
    await peer.send(0x48d);await peer.until(0x48f)
    assert sum(isinstance(e,Event)and e.kind==0xaf for e in observed[mark:])==notices
    assert economy(f.config.state_file,uid)==before
    cases.append(dict(stage=stage,part=part,key=npc['key'],source_index=npc['source_index']))
  assert len(cases)==13
  # Mutations target the exact static source check; the original actor and
  # catalogue are restored after each independent refusal.
  npc=actors[0];run=s.dungeon_run;old_actor=copy.deepcopy(npc);old_graph=run.graph;old_catalog=run.catalog;rejected=[]
  for field in('template','source_index','hp','points','start_point','no_drop','team','source_context','graph','script'):
   try:
    if field=='graph':run.graph=copy.deepcopy(old_graph);run.graph['source_sha256']='0'*64
    elif field=='script':run.catalog=copy.copy(old_catalog);run.catalog.manifest=copy.deepcopy(old_catalog.manifest);run.catalog.manifest['source_sha256']['Altera_Mine.lua']='0'*64
    elif field=='source_context':npc[field]=tuple([999,*npc[field][1:]])
    elif field=='points':npc[field]=[999]
    elif field=='no_drop':npc[field]=False
    else:npc[field]+=1
    try:value=flow.source_rule(run,npc)
    except ValueError:value=None
    assert value is None,field;rejected.append(field)
   finally:npc.clear();npc.update(copy.deepcopy(old_actor));run.graph=old_graph;run.catalog=old_catalog
  assert not any(e['event']in('worker_error','notification_error','protocol_error')for e in f.events)
  result.update(ok=True,accepted_sources=cases,economy_unchanged=True,retry_ACK_only=True,connections_kept=True,
   exact_source_mutations_rejected=rejected,finite_rule_count=len(rules.RULES),source_sha256=hashlib.sha256((C/'els_server/domain/scene_retirement_sources.py').read_bytes()).hexdigest())
  return result
 finally:await f.asyncTearDown()

if __name__=='__main__':
 try:result=asyncio.run(main())
 except BaseException:result=dict(ok=False,error=traceback.format_exc());raise
 finally:(H/'mine-TLS-fixed.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
