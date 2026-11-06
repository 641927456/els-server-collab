"""Installed-parent refusals; actual user-created scene helper and live catalogs."""
import json,struct,sys,types,uuid
from pathlib import Path
W=Path(__file__).resolve().parent;J=lambda p:json.loads(p.read_bytes());M=J(W/'candidate-manifest.json');parent='--parent'in sys.argv;D=Path(M['parent_runtime'])if parent else W/'runtime';sys.dont_write_bytecode=True;sys.path.insert(0,str(D))
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_spawns import handle
from els_server.domain.dungeon_npcs import encode_npc
from els_server.protocol.protocol_codec import Event
def request(t,creator):
 row=bytearray(0xa4);struct.pack_into('<ii',row,0,-1,t);row[0x4e]=1;struct.pack_into('<Q',row,0x6d,creator);return Event(0x202,kind=0x2ce,payload=struct.pack('>I',1)+encode_npc(row,0))
cases=M['dependency_paths']if parent else[p for p in M['dependency_paths']if p['target']==12585];results=[]
for chain in cases:
 run=DungeonRun(chain['dungeon'],str(uuid.uuid4()));run._load_stage(chain['stage']);run.part=next(k for k,v in run.parts.items()if any(n['template']==chain['root']for n in v['npcs']));creator=next(n['key']for n in run.current['npcs']if n['template']==chain['root']);s=types.SimpleNamespace(dungeon_run=run,phase='dungeon_active',population_test=True,dungeon_substage_synced=True,clear_notified=False,part_end_notified=False,account=types.SimpleNamespace(uid=1002,character=lambda:None),client_build='dx11_260923',role='game',summon_keys=set(),summon_deaths={},summon_requests={})
 for seq,edge in enumerate(chain['edges'][:-1],10):
  reply=handle(s,request(edge['target'],creator),seq);assert reply and reply[0].payload==bytes(4);creator=run.current['npcs'][-1]['key']
 before=len(run.current['npcs'])
 if parent:assert handle(s,request(chain['target'],creator),1)is None and len(run.current['npcs'])==before
 else:
  assert handle(s,request(chain['target'],99999999),1)is None and len(run.current['npcs'])==before
  event=request(chain['target'],s.account.uid);reply=handle(s,event,1);assert reply and reply[0].payload==bytes(4)and reply[1].kind==0x2d0;assert len(run.current['npcs'])==before+1 and run.current['npcs'][-1]['no_drop'];assert len(handle(s,event,1))==1 and len(run.current['npcs'])==before+1
 results.append(dict(dungeon=chain['dungeon'],stage=chain['stage'],target=chain['target'],parent_refused=parent,actual_user_creator_accepted=not parent,foreign_creator_rejected=not parent))
out=dict(ok=True,parent_negative=parent,cases=results,player_database_opened=False)
if not parent:
 from els_server.domain import dungeon_source_loot,dungeon_material_loot_catalog,dungeon_loot_catalog
 out['economic_catalog_maps']=[len(module.catalog()['maps'])for module in(dungeon_source_loot,dungeon_material_loot_catalog,dungeon_loot_catalog)];assert out['economic_catalog_maps']==[53,33,22]
(W/('parent-refusals.json'if parent else'user-creator-and-loot-tests.json')).write_text(json.dumps(out,indent=2)+'\n',encoding='utf8');print(json.dumps(out))
