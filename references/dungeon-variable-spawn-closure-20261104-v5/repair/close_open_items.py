"""Account for every prior unresolved call; never label absent source as decoded."""
import collections,hashlib,json,sys
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();M=J(W/'candidate-manifest.json');R=Path(M['parent_runtime']);sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(ROOT/'tools'),str(W.parents[1]/'remaining-v4')]
from els_server.game_data import client_data
from scope import original,kl
from symbolic_scan import scan
from flow_sources import Flow
data=client_data();enums=data.resource('Enum.lua');inputs=J(W/'all-variable-call-inputs.private.json');results=J(W/'flow-results-all.private.json');by_id={r['template']:r for r in results};records=[];manual=[]
for row in inputs:
 assert H(Path(row['path']))==row['sha256'];result=by_id[row['template']];assert 'error'not in result
 for case in result['calls']:
  item=dict(template=row['template'],script=row['script'],source_sha256=row['sha256'],prototype=case['prototype'],call_pc=case['call_pc'],targets=case['targets'],identity_witnesses=case['identity_witnesses'])
  symbolic=[s for s in case['unknown']if s.startswith("('")]
  if not symbolic:
   assert case['targets'];item['status']='finite_source_enum_domain'if not case['unknown']else'finite_source_enum_domain_with_nonidentity_state_values_excluded'
   if case['unknown']:item['excluded_nonidentity_values']=case['unknown']
  elif row['template']in(1410,1826)and case['prototype']==4:
   dump=kl.read(Path(row['path']).read_bytes());root=dump['prototypes'][dump['root']];name='SummonRandomMonsterIfCanDoIt'
   reads=[(pi,pc)for pi,p in enumerate(dump['prototypes'])for pc,(op,a,c,b)in enumerate(p['instructions'],1)if op==62 and p['kgc'][c|b<<8]==name]
   assert not reads;assert name in root['kgc']
   item.update(status='unreferenced_legacy_helper',helper=name,global_reads_in_registered_script=0,external_original_resource_reference_search='Only the two defining original Karis files matched the exact helper name; not a registered native state callback.')
  elif row['template']in(6944,7174,12578):
   dump=kl.read(Path(row['path']).read_bytes());pr=dump['prototypes'][case['prototype']];missing=[token for token in pr['kgc']if isinstance(token,str)and token.startswith('NUI_')and token not in enums['NPC_UNIT_ID']]
   assert missing and not case['targets'];item.update(status='no_current_enum_registration',missing_names=missing,scope='Original code references no current NPC identity here. No guessed replacement identity or blanket admission.')
  elif row['template']==1367:
   assert case['prototype']==11 and case['call_pc']==14
   graph=J(R/'els_server/data/client/dungeon_routes.json')['graphs']['dungeon_defence_normal.lua'];allowed=set(graph['stages']['0']['allowed_summons']);assert set(case['targets'])<=allowed
   # This legacy source already declares all original A/B/C families. Retain
   # its finite mode admission; a numeric state counter is not a new template.
   dump=kl.read(Path(row['path']).read_bytes());bases={name for p in dump['prototypes']for name in p['kgc']if isinstance(name,str)and name.startswith('NUI_GOD_')and name.endswith('_A')}
   family={enums['NPC_UNIT_ID'][base[:-1]+suffix]for base in bases for suffix in('A','B','C')if base[:-1]+suffix in enums['NPC_UNIT_ID']};assert family and family<=allowed
   item.update(status='existing_finite_original_mode_domain_preserved',dungeon=38300,declared_original_family_templates=len(family),original_family_fully_admitted=True,numeric_counter_not_new_identity=True,natural_counter_progression_verified=False)
  else:raise AssertionError(('Unclassified source call',row['template'],case))
  records.append(item)
assert len(records)==489
original_cases={(r['template'],c['prototype'],c['call_pc'])for r in J(W/'variable-call-inputs.private.json')for c in r['calls']};assert len(original_cases)==475
assert original_cases<={(r['template'],r['prototype'],r['call_pc'])for r in records}
# Pin the real original utility implementation behind the finite subset rule.
N=ROOT/'analysis/npc-client-native-values-20261025-v1/continuation-v2';utility=N/'global-resources/data036.kom/NPC_Util.lua';ledger=next(r for r in map(json.loads,(N/'global-decode-ledger.jsonl').read_text('utf8').splitlines())if r['name']=='NPC_Util.lua');assert H(utility)==ledger['plain_sha256'];dump=kl.read(utility.read_bytes());root=scan(dump)[dump['root']];bindings={}
for write in root['writes']:
 if write.get('key')in('ShuffleTable','ShuffleTable_RandSeed'):
  child=write['value']['args'][0];p=dump['prototypes'][child];assert p['parameters']==(4 if write['key']=='ShuffleTable' else 5);assert set(p['kgc'])=={'NPC','DeepCopy','PopRandomIndex','GetRandVal'}
  assert p['instructions'][-1][0]==76
  bindings[write['key']]=dict(prototype=child,parameters=p['parameters'],instruction_sha256=hashlib.sha256(json.dumps(p['instructions']).encode()).hexdigest(),original_input_table_parameter=2,semantics='DeepCopy source items then PopRandomIndex into a fresh result; result identities are a subset of the source table. No random weight or probability policy inferred.')
assert set(bindings)=={'ShuffleTable','ShuffleTable_RandSeed'}
# Full archive indexes distinguish absence from decode failure/ambiguity.
indexes={name:J(N/name)for name in('current-index.json','global-resource-index.json')};names={r['Name'].lower()for index in indexes.values()for r in index['rows']};source=J(W/'source-qualification.private.json');absent=[]
for key,reason in source['unresolved'].items():
 if isinstance(reason,dict):continue
 definition=data.npc(int(key));assert definition['script'].lower()not in names
 absent.append(dict(template=int(key),script=definition['script'],exact_original_archive_entries=0,registered_identity_preserved=True,original_Lua_restored=False,other_mode_script_substitution=False,Lua_outgoing_calls_available=False,scope='No original Lua entry exists to parse in this fixed client corpus; not an unresolved decode and not a replacement script. Native behavior of this missing original resource is not claimed verified.'))
assert len(absent)==6 and{8127,12829,12800,12801}<={r['template']for r in absent}
out=dict(ok=True,original_variable_scripts=160,original_variable_calls=475,expanded_variable_scripts=172,expanded_variable_calls=489,unclassified_calls=0,status_counts=dict(collections.Counter(r['status']for r in records)),calls=records,source_asset_boundaries=absent,original_utility=dict(path=str(utility),sha256=H(utility),archive_sha256=ledger['archive_sha256'],bindings=bindings),source_index_pins={name:H(N/name)for name in indexes},server_candidate_stage_dependencies=len(M['dependency_paths']),no_original_client_file_modified=True,no_natural_all_dungeon_clear_claim=True)
(W/'unclosed-items-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in out.items()if k not in('calls','source_asset_boundaries','original_utility','source_index_pins')}))
