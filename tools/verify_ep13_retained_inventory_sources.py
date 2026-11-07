"""Check the exact dual-installed reader definitions without private runtime assets."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'references/ep13-retained-inventory-20261101-v1'
contract=json.loads((REF/'source-contract.json').read_bytes())
for row in contract['source']:
    data=(REF/'source'/row['path']).read_bytes()
    assert len(data)==row['size']and hashlib.sha256(data).hexdigest()==row['sha256'],row['path']
raw=(REF/'source/els_server/data/retained_native_consumables.json').read_bytes();data=json.loads(raw)
tree=ast.parse((REF/'source/els_server/domain/retained_native_consumables.py').read_bytes())
assignments={n.targets[0].id:n.value for n in tree.body if isinstance(n,ast.Assign)and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)}
assert ast.literal_eval(assignments['DATA_SHA'])==hashlib.sha256(raw).hexdigest()
templates=ast.literal_eval(assignments['TEMPLATES'].args[0]);rows={r['template']:r for r in data['items']}
assert len(rows)==len(data['items'])==len(templates)==50 and set(templates)==set(rows)
assert not data['new_sources']and not data['consumption_enabled']and not contract['new_sources']and not contract['new_schema']
base=data['items'][:contract['base_item_count']]
assert hashlib.sha256(json.dumps(base,sort_keys=True,separators=(',',':')).encode()).hexdigest()==contract['base_items_sha256']
added={r['template']:r for r in data['items'][contract['base_item_count']:]}
assert set(added)==set(contract['added_templates'])=={716611,718783,720017,720835}
assert {t:(r['metadata'],r['group'],r['owned_max_stack'])for t,r in added.items()}=={716611:(0,4,1),718783:(0,4,1),720017:(2,4,999),720835:(2,4,1000)}
proof=json.loads((REF/'native-result.json').read_bytes());assert proof['ok']and not proof['client_process_access']
assert {r['template']for r in proof['rows']}==set(added)
for r in proof['rows']:assert r['ok']==1 and r['consumed']==304 and r['group']==4 and r['record_sha256']==added[r['template']]['record_sha256']
print(json.dumps(dict(ok=True,source_files=2,old_rows_preserved=len(base),new_readers=4,native_vectors=len(proof['rows']),runtime_database_access=False)))
