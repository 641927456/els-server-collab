"""Portable integrity checks for immutable F component review inputs."""
from pathlib import Path,PurePosixPath
import ast,hashlib,json,re
R=Path(__file__).resolve().parents[1]
def verify():
 reports=[]
 for A in sorted((R/'references').glob('f-service-*-20261026-v1')):
  m=json.loads((A/'manifest.json').read_bytes());assert m['schema']==1 and m['issue']in(518,519,520)
  assert m['runtime_overlay_not_main']and m['reference_snapshots_not_final_deployment_parent']and m['actual_parent_reconciliation_required']and not m['private_data_included']
  assert m['client_delta']==m['install_DDL_statements']==0 and m['new_lazy_tables']in(0,2)
  seen=set();assert set(m['channels'])=={'online','local'}
  for ch,b in m['channels'].items():
   assert re.fullmatch('[0-9a-f]{64}',b['reference_parent_manifest_sha256'])and sorted(r['path']for r in b['files'])==m['source_paths']
   for row in b['files']:
    rel=PurePosixPath(row['path']);loc=PurePosixPath(row['archive'])
    assert not rel.is_absolute()and '..'not in rel.parts and ':'not in str(rel)and str(rel).startswith('els_server/')
    assert str(loc)in('shared/'+str(rel),ch+'/'+str(rel))
    p=A/str(loc);assert p.resolve().is_relative_to(A.resolve())and not p.is_symlink();raw=p.read_bytes()
    assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
    if rel.suffix=='.py':ast.parse(raw)
    else:json.loads(raw)
    seen.add(str(loc))
  assert len(seen)==m['physical_source_files']
  for row in m['auxiliary_files']:
   p=PurePosixPath(row['path']);assert len(p.parts)==1 and p.suffix in('.txt','.json')and p.name!='manifest.json'
   assert hashlib.sha256((A/str(p)).read_bytes()).hexdigest()==row['sha256'];seen.add(str(p))
  assert {p.relative_to(A).as_posix()for p in A.rglob('*')if p.is_file()}==seen|{'manifest.json'}
  reports.append(dict(issue=m['issue'],channel_source_paths=len(m['source_paths']),physical_source_files=m['physical_source_files']))
 return dict(ok=True,components=reports,formal_deployment_claimed=False,database_opened=False)
if __name__=='__main__':print(json.dumps(verify()))
