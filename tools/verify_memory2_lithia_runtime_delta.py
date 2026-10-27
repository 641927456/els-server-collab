"""Verify the finite reviewed two-mode source archive without App or databases."""
from pathlib import Path,PurePosixPath
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/memory2-lithia-native-completion-20261026-v1'
EXPECTED={
 'els_server/domain/scene_actor_retirements.py','els_server/domain/dungeon_flow.py',
 'els_server/domain/story_controller_retirements.py','els_server/domain/local_session.py',
 'els_server/domain/regional_boss_cubes_legacy.py','els_server/storage/fixed_cubes.py',
 'els_server/storage/regional_boss_cube_source.py','els_server/data/regional_boss_cubes_lithia.json'}
NEW={'els_server/domain/scene_actor_retirements.py','els_server/data/regional_boss_cubes_lithia.json'}

def verify():
 m=json.loads((ARCHIVE/'manifest.json').read_bytes())
 assert m['schema']==1 and m['client_delta']==m['install_DDL_statements']==0
 assert set(m['channels'])=={'online','local'}and set(m['delta_paths'])==EXPECTED and set(m['new_paths'])==NEW
 assert m['unit15_pool_contents']=='explicitly-approved-local-supplement'
 assert m['primary_86_data_unchanged']and not m['private_configuration_or_player_data_included']
 seen=set();counts={}
 for ch,row in m['channels'].items():
  assert len(row['parent_manifest_sha256'])==64
  assert {x['path']for x in row['delta']}==EXPECTED
  assert {x['path']for x in row['delta']if x['parent_sha256']is None}==NEW
  for x in row['delta']:
   rel=PurePosixPath(x['path']);loc=PurePosixPath(x['archive'])
   assert not loc.is_absolute()and '..'not in loc.parts and ':'not in str(loc)and '\\'not in str(loc)
   assert str(loc)in ('shared/'+str(rel),ch+'/'+str(rel))
   p=ARCHIVE/loc;assert p.resolve().is_relative_to(ARCHIVE.resolve())and not p.is_symlink()
   raw=p.read_bytes();assert len(raw)==x['size']and hashlib.sha256(raw).hexdigest()==x['sha256']
   if rel.suffix=='.py':compile(raw,str(loc),'exec')
   else:json.loads(raw)
   seen.add(str(loc))
  counts[ch]=len(row['delta'])
 assert {p.relative_to(ARCHIVE).as_posix()for p in ARCHIVE.rglob('*')if p.is_file()}==seen|{'manifest.json'}
 assert len(seen)==m['physical_files']
 return dict(ok=True,channels=counts,physical_files=len(seen),database_opened=False)

if __name__=='__main__':print(json.dumps(verify()))
