from pathlib import Path
import ast,hashlib,json
R=Path(__file__).resolve().parents[1];A=R/'references/force-categories-sources-20261031-v1';c=json.loads((A/'source-contract.json').read_bytes());seen=set()
for name,ch in c['channels'].items():
 assert len(ch['files'])==24
 for row in ch['files']:
  p=R/row['source'];raw=p.read_bytes();assert p.resolve().is_relative_to(A.resolve())and hashlib.sha256(raw).hexdigest()==row['sha256']and len(raw)==row['size'];seen.add(row['source']);ast.parse(raw)if p.suffix=='.py'else json.loads(raw)
 assert hashlib.sha256((R/ch['patch']['path']).read_bytes()).hexdigest()==ch['patch']['sha256']
assert len(seen)==c['unique_source_files']and c['client_changes']is False and c['install_DDL']==0
books=json.loads((R/next(r['source']for r in c['channels']['local']['files']if r['path'].endswith('/native_force_catalog.json'))).read_bytes())
assert len(books['books'])==70 and len(books['exchanges'])==62 and len(books['recipes'])==24
assert len({r['skill']for r in books['books']if not r['active']})==14
assert len({r['exclusion_group']for r in books['books']if r['active']})==15
assert set(books['challenge_cube']['entries'][i]['template']for i in range(4))=={43677,43678,43773,43774}
print(json.dumps(dict(ok=True,channels=2,files_each=24,unique_sources=len(seen),common_books=70,exchanges=62)))
