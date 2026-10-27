"""Portable exact F transfer archive validation without game imports or SQL."""
from pathlib import Path,PurePosixPath
import ast,hashlib,json,re
R=Path(__file__).resolve().parents[1];A=R/'references/f-chip-circuit-transfer-20261026-v1'
def verify():
 m=json.loads((A/'manifest.json').read_bytes());assert m['schema']==1 and m['issue']==514
 assert m['runtime_overlay_not_main']and m['final_parent_qualification_verified']and not m['private_configuration_or_player_data_included']
 assert m['client_delta']==0 and not m['new_schema']and m['install_DDL_statements']==0
 assert set(m['channels'])=={'online','local'}and len(m['source_paths'])==6
 seen=set();values={}
 for ch,b in m['channels'].items():
  assert re.fullmatch('[0-9a-f]{64}',b['parent_manifest_sha256'])
  assert sorted(r['path']for r in b['files'])==m['source_paths']and sum(r['parent_sha256']is None for r in b['files'])==5
  for row in b['files']:
   rel=PurePosixPath(row['path']);loc=PurePosixPath(row['archive'])
   assert not rel.is_absolute()and '..'not in rel.parts and ':'not in str(rel)and '\\'not in str(rel)and str(rel).startswith('els_server/')
   assert str(loc)in('shared/'+str(rel),ch+'/'+str(rel))
   p=A/loc;assert p.resolve().is_relative_to(A.resolve())and not p.is_symlink();raw=p.read_bytes()
   assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
   assert row['parent_sha256']is None or re.fullmatch('[0-9a-f]{64}',row['parent_sha256'])
   if rel.suffix=='.py':ast.parse(raw)
   else:json.loads(raw)
   seen.add(str(loc));values[ch,str(rel)]=raw
  policy=values[ch,'els_server/data/chip_circuit_transfer.json'];p=json.loads(policy)
  assert len(p['pairs'])==len(set(map(tuple,p['pairs'])))==900 and len(p['records'])==120
  assert p['additional_ed']==0 and p['additional_materials']==[]and p['fee_is_explicit_local_rule']and p['source_must_have_both']
  assert p['groups']==[27,28]
  code=values[ch,'els_server/domain/chip_circuit_transfer_rules.py'].decode('utf8');match=re.search(r"DATA_SHA = '([0-9a-f]{64})'",code)
  assert match and match[1]==hashlib.sha256(policy).hexdigest()
  flow=values[ch,'els_server/domain/local_session.py'].decode('utf8');assert flow.count('chip_circuit_transfer_reply=chip_circuit_transfer_handle(self,event,request_sequence)')==1
 assert len(seen)==m['physical_source_files']==7
 for row in m['auxiliary_files']:
  rel=PurePosixPath(row['path']);assert len(rel.parts)==1 and rel.suffix in('.json','.txt')and rel.name!='manifest.json'
  assert hashlib.sha256((A/rel).read_bytes()).hexdigest()==row['sha256'];seen.add(str(rel))
 assert {p.relative_to(A).as_posix()for p in A.rglob('*')if p.is_file()}==seen|{'manifest.json'}
 return dict(ok=True,physical_sources=7,channel_delta_each=6,database_opened=False,formal_deployment_claimed=False)
if __name__=='__main__':print(json.dumps(verify()))
