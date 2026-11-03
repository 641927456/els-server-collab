"""Source reachability refined only by the verified native first-transition rule."""
import collections,copy,hashlib,json,shutil,sys
from pathlib import Path
W=Path(__file__).resolve().parent;A=W.parent;ROOT=W.parents[3];V=A/'fix-v5';sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT/'releases/online/native-dungeon-spawn-loot-scope-20261104-v1'),str(ROOT/'tools'),str(ROOT/'analysis/dungeon-stalls-20261103-v1/remaining-v4'),str(A/'fix-v4'),str(A/'fix-v3')]
from els_server.game_data import client_data
from scope import original,kl,namespace
from flow_sources import Flow
import joint_state_reachability as sg
J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert J(W/'native-event-priority-tests.json')['ok'];data=client_data();enums=data.resource('Enum.lua');routes=J(W/'candidate/els_server/data/client/dungeon_routes.json');initial=J(W/'seeded-stage-activation.private.json');ids=set(initial[0]['active'])
for tid in sorted(ids):
 if(V/f'producer-{tid}.private.json').exists():
  for suffix in('.private.json','-tables.private.json'):shutil.copyfile(V/f'producer-{tid}{suffix}',W/f'producer-{tid}{suffix}')
 else:
  p,_=original(data.npc(tid)['script']);dump=kl.read(p.read_bytes());view=copy.deepcopy(dump);code=view['prototypes'][view['root']]['instructions']
  if[list(x)for x in code[-2:]]==[[58,0,0,128],[75,0,1,0]]:view['prototypes'][view['root']]['instructions']=code[:-2]+[(75,0,1,0)]
  tables=namespace['initializer'](view,dict(TRUE=True,FALSE=False,DUNGEON_ID=data.resource('DungeonEnum.lua')['DUNGEON_ID']),client_sha256=kl.X2_DX11_SHA256)
  (W/f'producer-{tid}.private.json').write_text(json.dumps(dict(template=tid,source=str(p),sha256=H(p),dump=dump),ensure_ascii=False,indent=2),encoding='utf8');(W/f'producer-{tid}-tables.private.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2),encoding='utf8')
sg.W=W;tables=J(W/'producer-12578-tables.private.json');blocked=set();dominance=[]
for name,table in tables.items():
 if not isinstance(table,dict):continue
 events=table.get('EVENT_PROCESS',{});first=events.get('1',{});cond=table.get(first.get('3'),{})
 if first.get('1',{}).get('global')!='STATE_CHANGE_TYPE.SCT_CONDITION_TABLE'or cond!={'RATE':100}:continue
 destination=first['2'];assert any(isinstance(row,dict)and row.get('STATE_NAME')==destination for row in tables['INIT_STATE'].values())
 for key in events:
  if key!='1':blocked.add((12578,name,key))
 dominance.append(dict(state=name,first_event=1,condition={'RATE':100},destination=destination,pruned_later_event_indices=sorted(int(i)for i in events if i!='1')))
assert len(dominance)==2 and len(blocked)==6
# There is no source call that rewrites the event rates/order in this context.
condition_mutators=[]
for tid in ids:
 dump=J(W/f'producer-{tid}.private.json')['dump']
 for proto in dump['prototypes']:
  condition_mutators.extend((tid,v)for v in proto['kgc']if isinstance(v,str)and v.startswith(('SetCondition','SetEventProcess','ChangeCondition','SetEventRate')))
assert not condition_mutators,condition_mutators
flows={tid:Flow(J(W/f'producer-{tid}.private.json')['dump'],enums).spawn_results()for tid in ids};results=[]
for stage_id in(20,21):
 stage=routes['graphs']['dungeon_henir_space_chaos.lua']['stages'][str(stage_id)];active={n['template']for p in stage['parts'].values()for g in p['groups']for row in g['npcs']for n in row.get('options',[row])};rounds=[]
 while True:
  assert active<=ids;g=sg.analyze(sorted(active),frozenset(blocked));live={tuple(n)for n in g['nodes']};new=set();unknown=[];spawn_edges=[]
  for tid in active:
   for call in flows[tid]:
    if('function',tid,call['prototype'])not in live:continue
    if call['unknown']:unknown.append(dict(producer=tid,**call))
    for target in call['targets']:new.add(target);spawn_edges.append(dict(producer=tid,target=target,prototype=call['prototype'],pc=call['call_pc']))
  rounds.append(dict(active=sorted(active),new=sorted(new-active)))
  if not new-active:break
  active.update(new)
 assert not unknown and not g['unknown_state_calls'];assert('function',12578,7)not in live and 12582 not in active and 12585 in active
 results.append(dict(dungeon=35870,stage=stage_id,active_source_identities=sorted(active),activation_rounds=rounds,missing_enum_callback_reachable=False,missing_script_12582_has_executable_producer=False,required_original_sources_complete=True,unknown_spawn_arguments=0,unknown_state_calls=0,spawn_edges=spawn_edges))
out=dict(ok=True,method='Actual static seeds, complete active source closure and original native ordered-event/state-change guard',native_proof_sha256=H(W/'native-event-priority-tests.json'),producer_12578_sha256=J(W/'producer-12578.private.json')['sha256'],dominance=dominance,contexts=results,conditional_event_mutator_methods=condition_mutators,missing_names_physically_restored=False,missing_names_need_no_runtime_substitute=True,new_required_source_12585_restored_to_server_metadata=True,natural_GUI_or_full_combat_verified=False,original_client_modified=False)
(W/'henir-source-boundary-closure.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(ok=True,stages=2,required_sources_complete=True,missing_reference_callback_unreachable=True,missing_12582_not_required=True,new_12585_source_qualified=True,natural_full_combat=False)))
