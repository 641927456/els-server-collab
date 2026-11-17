"""Close this installed foundation batch; the wider feature audit continues."""
from common import *
held()
names=('online-installation-acceptance.json','local-runtime-acceptance.json','launcher-installation.json',
    'unified-runtime-parity.json','new-schema-acceptance.json','progress-readback.json',
    'publication-stage-cleanup.json','owned-cache-cleanup.json','QA-backups-compacted.json')
proofs={name:read(P/name)for name in names};assert all(v['ok']for v in proofs.values())
online,local,launcher=(read(R/f'releases/{ch}/current.json')for ch in('online','local','launchers'))
build=read(D/'build.json')
assert online['release']==RID and online['manifest_sha256']==sha(R/online['path']/'rollup-manifest.json')
assert local['manifest_sha256']==sha(R/local['path']/'local-business-manifest.json')
assert launcher['V']==106 and sha(launcher['path'])==build['exe_sha256']==launcher['sha256']
assert read(R/'releases/launchers/standalone-current.json')==launcher
assert online['launcher_release']==launcher['release']and online['local_release']==local['release']
assert read(H/'built-runtime-qualification.json')['panel_IP_hidden']
requirements=read(P/'requirements.json');pid=read(P/'online-journal-readback.json')['journal']['new_pid']
arguments='RID='+repr(RID)+'\nMANIFEST='+repr(online['manifest_sha256'])+'\nGATE='+repr(requirements['gate_path'])+'\nSTAGE='+repr(STAGE)+'\nPID='+str(pid)+'\n'
actual=remote(arguments+'''from pathlib import Path
import json,hashlib,urllib.request,subprocess
R=Path('C:/ElsFriends');marker=R/('release-'+RID+'.json')
assert hashlib.sha256(marker.read_bytes()).hexdigest()==MANIFEST
assert not Path(GATE).exists()and not Path(STAGE).exists()and not(R/'run/release.lock').exists()
key=(R/'state/gm/access.key').read_text('ascii').strip()
state=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18765/api/status',headers={'X-GM-Key':key}),timeout=15))['result']
assert state['ready']and state['owned']and state['pid']==PID
result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-Command',"@(Get-ScheduledTask -TaskName 'ELS-Achievement-Guild-Banner-Power-Publication-20261108-v1*' -ErrorAction SilentlyContinue).Count"],capture_output=True,timeout=30)
assert result.returncode==0 and result.stdout.decode('utf-8-sig').strip()=='0'
print(json.dumps(dict(ok=True,ready=True,same_observed_PID=True,ordinary_player_entry_open=True,own_publication_tasks_remaining=0,own_stage_remaining=False)))
''')
save(P/'final-online-health.json',actual)
save(P/'final-three-channel-acceptance.json',dict(ok=True,online_release=RID,local_release=local['release'],launcher_release=launcher['release'],launcher_version=106,
    launcher_exe_sha256=launcher['sha256'],panel_IP_hidden=True,local_IP='127.0.0.1',source_PR=plan['source_PR'],source_head=plan['source_head'],
    Git_submitted=True,Git_merge=False,online_installed=True,local_installed=True,launcher_installed=True,ordinary_entry_open=True,
    same_server_source=True,same_signed_runtime=True,online_observation_seconds=proofs['online-installation-acceptance.json']['observation_seconds'],
    local_observation_seconds=proofs['local-runtime-acceptance.json']['observation']['observation_seconds'],launcher_observation_seconds=proofs['launcher-installation.json']['observation_seconds'],
    online_progress_readback=True,own_QA_cleaned=True,own_stage_and_tasks_retired=True,own_caches_removed=True,
    own_cache_cleanup_scope='Four runtime/updater caches',retained_property_metadata_caches=3,
    property_metadata_cleanup_rejected_by_policy=True,
    original_EXE_KOM_changes=0,player_database_restore=False,natural_GUI=False,natural_battle=False,
    connected_source_types=47,connected_definitions=318,remaining_source_types=13,unresolved_original_reward_groups=53,
    remaining='13 other achievement source types, original rewards, achievement movement benefits and natural GUI; other previously retained feature audit gaps remain.',
    proofs={name:dict(path=str(P/name),sha256=sha(P/name))for name in names}))
(P/'release-owned-locks').write_text('Qualified guild-banner and native-power achievement sources V106 accepted; the remaining project scope continues.','utf8')
print(json.dumps(dict(ok=True,three_channels_installed=True,launcher_version=106,panel_IP_hidden=True,progress_published=True,own_publication_locks_release_requested=True,all_project_work_complete=False)))
