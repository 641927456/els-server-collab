"""Use the shared CFG flow for every native spawn call, including CALLM."""
import collections,hashlib,importlib.util,json,sys,time
from pathlib import Path
W=Path(__file__).resolve().parent;A=W.parent;ROOT=W.parents[3];R=ROOT/'releases/online/native-dungeon-spawn-loot-scope-20261104-v1';N=ROOT/'analysis/npc-client-native-values-20261025-v1/continuation-v2';sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(A/'fix-v7/candidate/tools'),str(ROOT/'tools')]
from els_server.game_data import client_data,CLIENT_SHA
from npc_spawn_source_flow import Flow
from read_kl_bytecode import read
sp=importlib.util.spec_from_file_location('canonical_builder',A/'fix-v7/candidate/tools/build_dungeon_routes.py');builder=importlib.util.module_from_spec(sp);sp.loader.exec_module(builder)
J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();routes=J(R/'els_server/data/client/dungeon_routes.json');data=client_data();enums=data.resource('Enum.lua');flow_sha=H(A/'fix-v7/candidate/tools/npc_spawn_source_flow.py');cache_dir=W/'flow-cache';cache_dir.mkdir(exist_ok=True)
ledger={r['name'].lower():r for n in('decode-ledger.jsonl','global-decode-ledger.jsonl')for r in map(json.loads,(N/n).read_text('utf8').splitlines())};memory={};errors={};started=time.monotonic();only_henir='--henir'in sys.argv
def dependencies(tid):
 if tid in memory:return memory[tid]
 definition=data.npc(tid);entry=ledger.get(definition['script'].lower())
 if entry is None:errors[tid]=dict(script=definition['script'],reason='no pinned decoded source');memory[tid]=[];return []
 p=Path(entry['path']);assert entry['client_sha256']==CLIENT_SHA and H(p)==entry['plain_sha256'];cache=cache_dir/(entry['plain_sha256']+'.json')
 if cache.exists():
  row=J(cache);assert row['flow_sha256']==flow_sha and row['client_sha256']==CLIENT_SHA
 else:
  dump=read(p.read_bytes());tokens={s.lower()for pr in dump['prototypes']for s in pr['kgc']if isinstance(s,str)};calls=Flow(dump,enums).spawn_results()if tokens&{'createnpcreq_lua','createnpchostreq_lua'}else[];special=builder.special_riding_target(dump,enums)
  row=dict(script=p.name,source_sha256=entry['plain_sha256'],flow_sha256=flow_sha,client_sha256=CLIENT_SHA,calls=calls,special_riding_target=special);cache.write_text(json.dumps(row,indent=2),encoding='utf8')
 out=[]
 for call in row['calls']:
  for target in call['targets']:out.append(dict(producer=tid,target=target,script=row['script'],source_sha256=row['source_sha256'],prototype=call['prototype'],pc=call['call_pc'],identity_witnesses=[w for w in call['identity_witnesses']if w[1]==target]))
 if row['special_riding_target']is not None:out.append(dict(producer=tid,target=row['special_riding_target'],script=row['script'],source_sha256=row['source_sha256'],prototype=None,pc=None,method='INIT_SPECIAL_RIDING_TARGET'))
 memory[tid]=out
 if len(memory)%30==0:print(json.dumps(dict(scripts=len(memory),seconds=round(time.monotonic()-started,1))),flush=True)
 return out
paths=[];summary=[]
for name,g in routes['graphs'].items():
 mids=[int(k)for kind in('routes','internal_routes','event_routes')for k,v in routes[kind].items()if v['source']==name]
 if not mids or only_henir and name!='dungeon_henir_space_chaos.lua':continue
 for sid,stage in g['stages'].items():
  roots={n['template']for p in stage['parts'].values()for group in p['groups']for row in group['npcs']for n in row.get('options',[row])};pending=list(roots);seen=set(roots);parent={}
  while pending:
   producer=pending.pop()
   for edge in dependencies(producer):
    target=edge['target']
    if target in seen:continue
    seen.add(target);pending.append(target);parent[target]=edge
  missing=seen-set(stage['allowed_summons'])
  for tid in sorted(missing):
   chain=[];cursor=tid
   while cursor not in roots:e=parent[cursor];chain.insert(0,e);cursor=e['producer']
   for mid in mids:paths.append(dict(dungeon=mid,source=name,stage=int(sid),target=tid,root=cursor,edges=chain))
  if missing:summary.append(dict(source=name,stage=int(sid),maps=mids,missing=sorted(missing)))
suffix='-henir'if only_henir else'';out=dict(ok=True,client_sha256=CLIENT_SHA,flow_sha256=flow_sha,all_spawn_opcodes_use_shared_flow=True,scripts=len(memory),source_errors=errors,paths=paths,rows=summary,seconds=time.monotonic()-started)
(W/('full-source-closure'+suffix+'.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(ok=True,scripts=len(memory),maps=len({p['dungeon']for p in paths}),stage_targets=len(paths),targets=sorted({p['target']for p in paths}),source_errors=len(errors),seconds=round(out['seconds'],1))),flush=True)
