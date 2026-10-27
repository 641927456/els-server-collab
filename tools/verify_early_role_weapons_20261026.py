"""Verify exact finite dual-channel source delta, without App/database access."""
from pathlib import Path,PurePosixPath
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/early-role-eight-weapons-20261026-v1'
EXPECTED={'els_server/data/formal_pve_economy.json', 'els_server/data/early_weapon_equipment.json', 'els_server/domain/early_weapon_equipment.py', 'analysis/original-feedback-continuation-20261026-v1/weapons/native-weapons-proof-v1.json', 'els_server/domain/equipment_instance.py', 'els_server/domain/equipment_eligibility.py', 'els_server/domain/instance_stats.py', 'els_server/data/formal_pve_economy.manifest.json', 'els_server/domain/normal_equipment.py'}
NEW={'els_server/data/early_weapon_equipment.json', 'els_server/domain/early_weapon_equipment.py', 'analysis/original-feedback-continuation-20261026-v1/weapons/native-weapons-proof-v1.json'}
def verify():
 m=json.loads((ARCHIVE/'manifest.json').read_bytes())
 assert m['schema_version']==1 and m['issue']==531
 assert m['unit_ids']==['early-role-eight-native-weapons']
 assert m['client_delta']==m['install_DDL_statements']==0 and m['new_schema']is False
 assert m['old_evidence_unchanged']and not m['private_configuration_or_player_data_included']
 assert set(m['channels'])=={'online','local'}and set(m['delta_paths'])==EXPECTED and set(m['new_paths'])==NEW
 seen=set()
 for ch,row in m['channels'].items():
  assert len(row['parent_manifest_sha256'])==64
  assert {v['path']for v in row['delta']}==EXPECTED
  assert {v['path']for v in row['delta']if v['parent_sha256']is None}==NEW
  for v in row['delta']:
   rel=PurePosixPath(v['path']);loc=PurePosixPath(v['archive'])
   assert not loc.is_absolute()and '..'not in loc.parts and ':'not in str(loc)and '\\'not in str(loc)
   assert str(loc)=='shared/'+str(rel)
   p=ARCHIVE/loc;assert p.resolve().is_relative_to(ARCHIVE.resolve())and not p.is_symlink()
   raw=p.read_bytes();assert len(raw)==v['size']and hashlib.sha256(raw).hexdigest()==v['sha256']
   if rel.suffix=='.py':compile(raw,str(loc),'exec')
   else:json.loads(raw)
   seen.add(str(loc))
 assert len(seen)==m['physical_files']==9
 assert {p.relative_to(ARCHIVE).as_posix()for p in ARCHIVE.rglob('*')if p.is_file()}==seen|{'manifest.json'}
 return dict(ok=True,dual_delta_files=9,physical_files=9,new_files=3,database_opened=False)
if __name__=='__main__':print(json.dumps(verify()))
