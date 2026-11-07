"""Bind accepted channels to the already approved source and merge commit."""
from common import *
import copy
held()
for name in('online-installation-acceptance.json','local-runtime-acceptance.json','local-public-acceptance.json','launcher-installation.json','unified-runtime-parity.json','ordinary-entry-open.json'):
    assert read(P/name)['ok'],name
git=read(P/'git.json');build=read(D/'build.json')
channels={c:read(R/f'releases/{c}/current.json')for c in('online','local','launchers')}
assert channels['online']['release']==RID and channels['launchers']['V']==103
assert sha(channels['launchers']['path'])==build['exe_sha256']
online=R/channels['online']['path'];local=R/channels['local']['path']
for f in read(plan['candidate_manifest'])['files']:
    assert sha(online/f['path'])==sha(local/f['path'])==f['sha256']
for channel,old in channels.items():
    new=copy.deepcopy(old)
    new.pop('source_issue',None)
    new['inherited_parent_source_state']=read(P/'inherited-parent-source-state.json')
    new.update(source_PR=945,source_head=git['head'],source_merge_commit=git['merge_commit'],
        source_archive=plan['source_archive'],source_Git_submitted=True,Git_merge=True,current_delta_Git_merge=True,
        source_Git_merged=True,current_delta_PR=945,current_delta_head=git['head'],source_current_PR=945,
        source_current_head=git['head'],shared_runtime_archive_sha256=build['signed_bindings']['signedFriends']['archive']['sha256'])
    if channel in('online','local'):
        new.update(launcher_pending=False,local_shared_server_update_pending=False,
            launcher_release=channels['launchers']['release'],local_release=channels['local']['release'],
            same_server_source_for_both_targets=True,same_signed_definition_for_both_targets=True)
    path=R/f'releases/{channel}/current.json';assert read(path)==old
    temporary=path.with_name('current.disconnect-binding.next');save(temporary,new);os.replace(temporary,path)
    if channel=='launchers':save(R/'releases/launchers/standalone-current.json',new)
receipt=dict(ok=True,online_installed=True,local_installed=True,launcher_installed=True,
    online_release=RID,local_release=channels['local']['release'],launcher_release=channels['launchers']['release'],launcher_version=103,
    source_PR=945,source_head=git['head'],source_merge_commit=git['merge_commit'],Git_submitted=True,Git_merge=True,
    launcher_exe_sha256=build['exe_sha256'],shared_runtime_archive_sha256=build['signed_bindings']['signedFriends']['archive']['sha256'],
    online_manifest_sha256=channels['online']['manifest_sha256'],local_manifest_sha256=channels['local']['manifest_sha256'],
    server_source_identity=read(P/'unified-runtime-parity.json')['server_source_identity'],
    actual_installed_source_files=read(plan['candidate_manifest'])['files'],
    same_server_source=True,same_signed_runtime=True,local_IP='127.0.0.1',changed_source_files=8,
    online_observation_seconds=read(P/'online-installation-acceptance.json')['observation_seconds'],
    local_observation_seconds=read(P/'local-runtime-acceptance.json')['observation']['observation_seconds'],
    launcher_observation_seconds=read(P/'launcher-installation.json')['observation_seconds'],
    own_QA_cleaned=True,ordinary_entry_open=True,own_stage_and_caches_retired=False,
    original_EXE_KOM_changes=0,player_database_restore=False,natural_GUI=False,natural_battle=False,
    remaining='Native15-second heartbeat reaches the unprotected sender; exact live duplicate-body attribution remains pending. The historical5BFerror is ownedQA. Original1395death cleanup matches all five stage3targets; preceding triggerDTO remains unavailable. No native sendHook or new cleanup rule was installed.')
save(P/'final-three-channel-acceptance.json',receipt)
print(json.dumps(dict(ok=True,three_channels_bound_to_approved_head=True,launcher_version=103)))
