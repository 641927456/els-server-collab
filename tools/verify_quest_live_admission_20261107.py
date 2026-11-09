"""Verify exact delivered task source and public evidence without activating an engine."""
from pathlib import Path
import base64,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'refs/quest-live-admission-20261107-v1'
PIN='8b75f3dccd5f2f591aa830e27b2e828e07b12dda4ef9c0bf7a21747becd9e848'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def verify():
 assert sha(A/'manifest.json')==PIN
 m=json.loads((A/'manifest.json').read_bytes());assert m['issue']==916 and m['archive_only']and not m['default_engine_selection_changed']
 assert len(m['source_files'])==2 and len(m['launcher_source_files'])==3
 names=set()
 for row in m['files']:
  p=Path(row['path']);assert not p.is_absolute()and '..'not in p.parts and row['path']not in names;names.add(row['path'])
  source=A/p;assert source.stat().st_size==row['size']and sha(source)==row['sha256']
  if source.suffix=='.py':compile(source.read_bytes(),str(p),'exec')
  elif source.suffix=='.json':json.loads(source.read_bytes())
 assert {p.relative_to(A).as_posix()for p in A.rglob('*')if p.is_file()}==names|{'manifest.json'}
 v=json.loads((A/'validation.json').read_bytes());d=json.loads((A/'installed-summary.json').read_bytes());public=json.loads((A/'public-validation.json').read_bytes())
 assert v['ok']and v['isolated_tests']==13 and v['Application_worker_tests']==1 and v['failures']==v['errors']==v['skipped']==0
 assert v['source']=={r['runtime_path']:r['sha256']for r in m['source_files']}
 for name,digest in v['original_runner_sha256'].items():assert sha(A/name)==digest
 assert d['ok']and d['online_installed']and d['local_installed']and d['launcher_installed']and d['own_QA_cleaned']
 assert d['online_observation_seconds']>=120 and d['local_observation_seconds']>=120 and d['public_launcher_observation_seconds']>=120
 assert d['same_server_source']and d['same_signed_runtime']and d['signed_members']==2786 and not d['player_database_restore']
 for mode in ('online','local'):
  p=public[mode];assert p['ok']and p['cold_SQL_matches_live_F0']and p['no_automatic_reward']
  assert {q for r in p['checks']for q in r['new_live_tasks']}=={100020,100030,52700}
  assert all(not r['town_reload_after_reward']for r in p['checks'])
 wrapper=json.loads((A/'launcher-source/resources/ui-scroll-signedFriends.signed.json').read_bytes());definition=json.loads(base64.b64decode(wrapper['payload']))
 rows={r['path']:r for r in definition['files']};assert definition['archive']['sha256']==d['runtime_payload_sha256']
 for r in m['source_files']:assert rows[r['runtime_path']]['sha256']==r['sha256']
 cohort=(A/'launcher-source/UIScrollRuntimeCohort.cs').read_text('utf8')
 assert re.search(r'FriendsPayload="([a-f0-9]{64})"',cohort).group(1)==d['runtime_payload_sha256']
 assert re.search(r'FriendsEnvelope="([a-f0-9]{64})"',cohort).group(1)==sha(A/'launcher-source/resources/ui-scroll-signedFriends.signed.json')
 assert 'public const int Version = 85;'in(A/'launcher-source/AutoUpdate.cs').read_text('utf8')
 return dict(ok=True,source_files=2,launcher_inputs=3,isolated_and_worker_tests=14,actual_dual_native_quest_checks=True,default_engine_activated=False)
if __name__=='__main__':print(json.dumps(verify()))
