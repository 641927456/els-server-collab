import collections,copy,hashlib,importlib.util,json,statistics,struct,sys,types,uuid
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];D=W/'runtime';M=json.loads((W/'candidate-manifest.json').read_bytes());R=Path(M['parent_runtime'])
sys.dont_write_bytecode=True;sys.path[:0]=[str(D),str(ROOT/'tools')]
from els_server.domain.dungeon_routes import DungeonRun,route_catalog
from els_server.domain.dungeon_spawns import handle,decode
from els_server.domain.dungeon_npcs import encode_npc
from els_server.domain import formal_npc_hp as hp
from els_server.game_data import client_data,CLIENT_SHA
from els_server.protocol.protocol_codec import Event,encode_event
import read_kl_bytecode as kl
J=lambda p:json.loads(p.read_bytes())
sp=importlib.util.spec_from_file_location('fixed_collector',D/'tools/build_dungeon_routes.py');b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
index=b.verified_ai_sources(ROOT,CLIENT_SHA);en=client_data().resource('Enum.lua');sources=[]
for edge in M['qualified_edges']:
 p=index[edge['script'].lower()];assert hashlib.sha256(p.read_bytes()).hexdigest()==edge['sha256']
 assert edge['target']in b.summon_targets(kl.read(p.read_bytes()),en)
 sources.append((edge['producer'],edge['target']))
assert len(set(sources))==len({(e["producer"],e["target"])for e in M["qualified_edges"]})
# The old native riding declarations remain present through the same collector.
riding=[]
for row in J(W.parent/'spawn-source-scan.private.json')['producers']:
 if not any('SummonSpecialRidingNPC'in x['methods']for x in row['producers']):continue
 target=b.special_riding_target(kl.read(Path(row['path']).read_bytes()),en)
 assert target in b.summon_targets(kl.read(Path(row['path']).read_bytes()),en)
 for name,st in row['contexts']:assert target in route_catalog()._data['graphs'][name]['stages'][st]['allowed_summons']
 riding.append((row['template'],target))
assert len(riding)==8 and(9297,9306)in riding
results=[]
for item in M['qualified_maps']:
 for stage,targets in item['stage_additions'].items():
  for tid in targets:
   stage=int(stage);r=DungeonRun(item['dungeon'],str(uuid.uuid4()));r._load_stage(stage)
   chain=next(p for p in M['dependency_paths']if p['dungeon']==r.identity and p['stage']==stage and p['target']==tid)
   part,producer=next((part,n)for part,p in r.parts.items()for n in p['npcs']if n['template']==chain['root'])
   r.part=part;creator=producer['key']
   s=types.SimpleNamespace(dungeon_run=r,phase='dungeon_active',population_test=True,dungeon_substage_synced=True,clear_notified=False,part_end_notified=False,account=types.SimpleNamespace(uid=1002,character=lambda:None),client_build='dx11_260923',role='game',summon_keys=set(),summon_deaths={},summon_requests={})
   for seq,parent in enumerate(chain['edges'][:-1],10):
    raw=bytearray(0xa4);struct.pack_into('<ii',raw,0,-1,parent['target']);raw[0x4e]=1;struct.pack_into('<Q',raw,0x6d,creator)
    emitted=handle(s,Event(0x202,kind=0x2ce,payload=struct.pack('>I',1)+encode_npc(raw,0)),seq)
    assert emitted and emitted[0].payload==bytes(4)and emitted[1].kind==0x2d0
    creator=r.current['npcs'][-1]['key']
   dto=bytearray(0xa4);struct.pack_into('<ii',dto,0,-1,tid);struct.pack_into('<fff',dto,9,123.,456.,789.);dto[0x4e]=1;struct.pack_into('<Q',dto,0x6d,creator)
   body=struct.pack('>I',1)+encode_npc(dto,0);event=Event(0x202,kind=0x2ce,payload=body)
   count=len(r.current['npcs']);oldnext=r.next;oldready=r.ready_at;out=handle(s,event,1)
   assert out and[out[0].kind,out[1].kind]==[0x2cf,0x2d0]and out[0].payload==bytes(4)
   [encode_event(e)for e in out];assert len(r.current['npcs'])==count+1
   actor=r.current['npcs'][-1];assert actor['template']==tid and actor['no_drop']and actor['dynamic']and actor['hp']>0
   assert actor['wire']in out[1].payload and actor['init']in out[1].payload
   # Request decoder now correctly accepts only unallocated key=-1. Compare
   # the emitted native wire with the original DTO plus authoritative fields.
   wire=bytearray(dto);struct.pack_into('<i',wire,0,actor['key']);wire[8]=hp.level(r.catalog,r.identity)
   assert encode_npc(wire,0)==actor['wire']
   assert struct.unpack_from('<i',wire,4)[0]==tid and wire[8]==hp.level(r.catalog,r.identity)
   assert struct.unpack_from('<fff',wire,9)==(123.,456.,789.)
   expected_hp=hp.summoned_maximum(r,tid)[0]
   assert actor['hp']==expected_hp
   duplicate=handle(s,event,1);assert len(duplicate)==1 and duplicate[0].payload==bytes(4)and len(r.current['npcs'])==count+1
   conflict=handle(s,Event(0x202,kind=0x2ce,payload=body+b'\0'),1);assert len(conflict)==1 and conflict[0].payload==struct.pack('>i',1)
   invalid=bytearray(dto);struct.pack_into('<i',invalid,4,2147483647)
   bad=Event(0x202,kind=0x2ce,payload=struct.pack('>I',2)+encode_npc(dto,0)+encode_npc(invalid,0))
   before_requests=dict(r.dynamic_requests);assert handle(s,bad,2)is None and r.dynamic_requests==before_requests and len(r.current['npcs'])==count+1
   assert not r.defeated and r.next==oldnext and r.ready_at==oldready and not s.clear_notified and not s.part_end_notified
   other=DungeonRun(34120,str(uuid.uuid4()));s.dungeon_run=other;assert handle(s,event,9)is None
   results.append(dict(dungeon=r.identity,stage=stage,target=tid,hp=actor['hp'],level=wire[8],real_actor_and_2D0=True,duplicate_ACK_only=True,mixed_invalid_batch_atomic=True,foreign_map_rejects=True))
assert len(results)==len(M['dependency_paths'])
# Existing graph structure, formal identities, mode HP and all unrelated fields stay equal.
old=J(R/'els_server/data/client/dungeon_routes.json');new=copy.deepcopy(route_catalog()._data)
expected_changes={(x['source'],s)for x in M['qualified_maps']for s in x['stage_additions']}
changed=set()
for name,g in new['graphs'].items():
 for st,s in g['stages'].items():
  prev=old['graphs'][name]['stages'][st]
  if s['allowed_summons']!=prev['allowed_summons']:changed.add((name,st));s['allowed_summons']=prev['allowed_summons']
assert changed==expected_changes
for tid in M['new_native_metadata']:del new['npcs'][str(tid)]
assert new==old
for file in('formal_npc_hp.json','raid_npc_hp.json'):
 old=J(R/'els_server/data'/file);new=copy.deepcopy(J(D/'els_server/data'/file))
 if file=='formal_npc_hp.json':
  for tid in M['new_HP_identities']:del new['templates'][str(tid)]
  new['sources']['raid_local_policy']=old['sources']['raid_local_policy']
 else:
  for row in M['new_mode_HP_bindings']:del new['maps'][str(row['dungeon'])]['templates'][str(row['template'])]
  new['counts']=old['counts']
 assert new==old,file
# Independently recalculate each added local median from its retained same-mode pool.
reference=J(ROOT/'analysis/monster-economy-formal-20261025-v1/raid-audit-v1/public-raid-hp-reference.json')
audit=J(ROOT/'analysis/monster-economy-formal-20261025-v1/raid-audit-v1/current-raid-audit.json')
for item in M['new_mode_HP_bindings']:
 if item['source']!='local_same_mode_unique_role_median':continue
 mid=item['dungeon'];source=next(r for r in audit['rows']if r['map']==mid);roles=collections.defaultdict(set)
 for actor in source['actors']:roles[actor['template']].add(bool(actor['boss']))
 ref=reference['maps'][str(mid)]['templates'];pools={role:{t:ref[str(t)]['initial_HP_float32']for t,flags in roles.items()if flags=={role}and str(t)in ref}for role in(False,True)}
 pool=pools[False]or pools[True];entry=hp.raid_policy()['maps'][str(mid)]['templates'][str(item['template'])]
 assert entry['anchor_templates']==sorted(pool)and entry['anchor_values']=={str(k):v for k,v in pool.items()}
 assert item['hp']==hp.f32(statistics.median(pool.values()))
out=dict(ok=True,cases=results,existing_riding_declarations=len(riding),source_qualified_edges=len(set(sources)),existing_graphs_rosters_gates_rewards_and_HP_unchanged=True,current_player_summon_batch_source_unchanged=(D/'els_server/domain/friends_spawns.py').read_bytes()==(R/'els_server/domain/friends_spawns.py').read_bytes(),natural_combat=False)
(W/'dependency-domain-tests.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8');print(json.dumps(out))
