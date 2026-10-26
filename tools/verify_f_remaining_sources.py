"""Portable integrity checks for remaining F feature review snapshots."""
from pathlib import Path,PurePosixPath
import ast,hashlib,json,re
R=Path(__file__).resolve().parents[1]
def verify():
 reports=[]
 for A in sorted((R/'references').glob('f-remaining-*-20261026-v1')):
  m=json.loads((A/'manifest.json').read_bytes());assert m['schema']==1 and (m['issue'],m['component'])in((515,'ranking'),(524,'gauge'))
  assert m['review_snapshots_only']and m['actual_parent_reconciliation_required']and not m['private_data_included']
  seen={'manifest.json'};assert set(m['channels'])=={'online','local'}
  for ch,b in m['channels'].items():
   assert re.fullmatch('[0-9a-f]{64}',b['reference_parent_sha256'])
   assert len(b['files'])==m['delta_each']and sum(r['parent_sha256']is None for r in b['files'])==m['new_each']
   assert sorted(r['path']for r in b['files'])==m['source_paths']
   for r in b['files']:
    rel=PurePosixPath(r['path']);assert not rel.is_absolute()and '..'not in rel.parts and ':'not in str(rel)and str(rel).startswith('els_server/')
    assert r['archive']==ch+'/'+str(rel);p=A/r['archive'];assert p.resolve().is_relative_to(A.resolve())and not p.is_symlink();raw=p.read_bytes()
    assert len(raw)==r['bytes']and hashlib.sha256(raw).hexdigest()==r['sha256'];seen.add(r['archive'])
    if rel.suffix=='.py':ast.parse(raw)
    else:assert rel.suffix=='.json';json.loads(raw)
  for r in m['auxiliary_files']:
   p=PurePosixPath(r['path']);assert len(p.parts)==1 and p.suffix in('.json','.txt')and p.name!='manifest.json'
   assert hashlib.sha256((A/str(p)).read_bytes()).hexdigest()==r['sha256'];seen.add(str(p))
  assert {p.relative_to(A).as_posix()for p in A.rglob('*')if p.is_file()}==seen
  reports.append({'issue':m['issue'],'delta_each':m['delta_each']})
 return {'ok':True,'components':reports,'formal_deployment_claimed':False,'database_opened':False}
if __name__=='__main__':print(json.dumps(verify()))
