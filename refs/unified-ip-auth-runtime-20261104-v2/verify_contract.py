from pathlib import Path
import ast,hashlib,json
R=Path(__file__).resolve().parent;c=json.loads((R/'source-contract.json').read_bytes())
for n,h in (c['files']|c['evidence']).items():
 p=R/n;assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
 if p.suffix=='.py':ast.parse(p.read_text('utf-8-sig'))
assert c['archive_only']and not c['source_root_activation']and not c['automatic_deployment']and not c['production_data_included']
print('Exact archived source and sanitized evidence hashes verified')
