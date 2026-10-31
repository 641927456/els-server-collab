from pathlib import Path
import ast,hashlib,json
O=Path(__file__).resolve().parent;R=O.parents[1]
c=json.loads((O/'source-contract.json').read_bytes());assert c['issue']==707 and len(c['files'])==5
g=json.loads((O/'gui-qualification.json').read_bytes())
for f in c['files']:
 p=R/f['source'];assert p.is_relative_to(O/'source/shared')and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']==g['delivery_leaf_sha256'][f['path']]
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
for name in('map-model.json','sparse-model.json','sparse-server-qualified.json'):assert json.loads((O/name).read_bytes())['ok']
assert g['33232']['ok']and not g['33232']['prior_stage3_marker']and g['35301']['ok']and g['35301']['controlled_prior_room_and_final_stage_advance']
assert g['35301']['original_parser_count']==2 and g['35301']['native_second_ordinal']==1 and g['35301']['server_source_stage']==2
assert c['dependencies']['new_required_signed_leaves']==['tools/native_sparse_stages.py','tools/native_sparse_stages.js']
print(json.dumps(dict(ok=True,delivery_leaves=5,recorded_GUI_cases=2,source_contexts_retained=True,natural_full_clear=False,runtime_tests_reexecuted=False)))
