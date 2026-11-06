from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;m=json.loads((H/'source-manifest.json').read_bytes())
for row in m['files']:
 p=H/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
for r in m['changes']:
 assert hashlib.sha256((H/'source'/r['path']).read_bytes()).hexdigest()==r['sha256']
 assert hashlib.sha256((H/'base'/r['path']).read_bytes()).hexdigest()==r['parent_sha256']
v=json.loads((H/'validation.json').read_bytes());assert v['ok']and v['extra_static_entries']==40 and v['native_dungeon_types']==740 and v['cancelled_poll_publication_skipped']and v['cold_balance_verified']
print(json.dumps(dict(ok=True,exact_files=len(m['files']),runtime_delta=len(m['changes']),startup_and_cancel_validation=True)))
