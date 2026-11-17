"""Remove the revised and superseded own caches after deployment acceptance."""
from common import *
sys.path.insert(0,str(R/'tools/pylibs'))
import base64,psutil,shutil
held()
for name in('progress-readback.json','publication-stage-cleanup.json','local-runtime-acceptance.json','launcher-installation.json'):
    assert read(P/name)['ok'],name
local=read(P/'local-public-acceptance.json')['owned_QA_cleanup'];assert local['ok']and local['writer_barrier_passed']
assert not psutil.pid_exists(read(P/'local-actual-loaded.json')['pid'])
targets=[Path('G:/qa-ach105'),Path('G:/qa-ach106'),Path('G:/qa-ach106-net'),R/'qa-ach106-updater-20261108-v1']
assert {p.name for p in targets}=={'qa-ach105','qa-ach106','qa-ach106-net','qa-ach106-updater-20261108-v1'}
for path in targets:
    assert path.is_absolute()and path.resolve()==path and path.exists()
    assert path.parent in(Path('G:/'),R)
    assert read(path/'owner.json')==dict(thread=OWNER,release=RID)
    for entry in(path,*path.parents,*path.rglob('*')):
        assert not entry.is_symlink()and not entry.is_junction()and not(entry.lstat().st_file_attributes&0x400),str(entry)
for channel in('online','local','launchers'):
    value=json.dumps(read(R/f'releases/{channel}/current.json')).replace('\\\\','\\').replace('/','\\').lower()
    for path in targets:assert str(path).replace('/','\\').lower()not in value,'Current pointer references cache'
for process in psutil.process_iter(['pid','exe','cwd','cmdline']):
    try:
        info=process.info;value=' '.join([info.get('exe')or'',info.get('cwd')or'',*(info.get('cmdline')or[])]).replace('/','\\').lower()
        for path in targets:assert str(path).replace('/','\\').lower()not in value,('Cache process reference',process.pid,str(path))
    except(psutil.NoSuchProcess,psutil.AccessDenied):continue
script=r'''$ErrorActionPreference='Stop';$targets=TARGETS
foreach($task in Get-ScheduledTask){foreach($action in $task.Actions){$v=($action.Execute+' '+$action.Arguments+' '+$action.WorkingDirectory).Replace('/','\');foreach($p in $targets){if($v.IndexOf($p,[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'Scheduled task references cache'}}}}
$w=New-Object -ComObject WScript.Shell
foreach($link in Get-ChildItem -LiteralPath ([Environment]::GetFolderPath('Desktop')) -Filter '*.lnk'){$s=$w.CreateShortcut($link.FullName);foreach($p in $targets){if(($s.TargetPath+' '+$s.Arguments).Replace('/','\').IndexOf($p,[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'Shortcut references cache'}}}
'''
quote=lambda p:"'"+str(p).replace("'","''")+"'"
script=script.replace('TARGETS','@('+','.join(quote(path)for path in targets)+')')
result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],capture_output=True,timeout=50)
assert result.returncode==0,result.stderr.decode('utf8','replace')[-1200:]
rows=[dict(path=str(path),files=sum(p.is_file()for p in path.rglob('*')),bytes=sum(p.stat().st_size for p in path.rglob('*')if p.is_file()))for path in targets]
first=H/'launcher-preview-v105';failed=read(first/'build.json')
assert failed['version']==105 and failed['private_candidate'] and not failed['published']
assert failed['exe_sha256']=='d573ed6984bd31560959ea634320c7466520250e2a01ccf7b850c15575cec070'
payloads=[first/'assets',Path(failed['signed_bindings']['signedFriends']['archive']['path']),Path(failed['exe'])]
assert sha(payloads[1])==failed['signed_bindings']['signedFriends']['archive']['sha256']and sha(payloads[2])==failed['exe_sha256']
assert {p.name for p in payloads[0].iterdir()}=={c['file']for c in read(first/'runtime-files.json')['chunks']}|{payloads[1].name}
for path in payloads:
    assert path.is_absolute()and path.resolve().parent==first.resolve()
    for entry in(path,*path.rglob('*'))if path.is_dir()else(path,):
        assert not entry.is_symlink()and not entry.is_junction()and not(entry.lstat().st_file_attributes&0x400)
    for process in psutil.process_iter(['exe','cwd','cmdline']):
        try:
            info=process.info;text=' '.join([info.get('exe')or'',info.get('cwd')or'',*(info.get('cmdline')or[])]).replace('/','\\').lower()
            assert str(path).replace('/','\\').lower()not in text
        except(psutil.NoSuchProcess,psutil.AccessDenied):continue
for channel in('online','local','launchers'):
    value=json.dumps(read(R/f'releases/{channel}/current.json')).replace('\\\\','\\').replace('/','\\').lower()
    for path in payloads:assert str(path).replace('/','\\').lower()not in value
old_array='@('+','.join(quote(path)for path in targets)+')'
new_array='@('+','.join(quote(path)for path in payloads)+')'
assert script.count(old_array)==1
payload_script=script.replace(old_array,new_array)
result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',base64.b64encode(payload_script.encode('utf-16le')).decode()],capture_output=True,timeout=50)
assert result.returncode==0,result.stderr.decode('utf8','replace')[-1200:]
payload_rows=[dict(path=str(path),bytes=sum(p.stat().st_size for p in path.rglob('*')if p.is_file())if path.is_dir()else path.stat().st_size)for path in payloads]
save(P/'owned-cache-cleanup-plan.json',dict(thread=OWNER,release=RID,targets=rows,superseded_private_payloads=payload_rows,no_process_task_shortcut_references=True,no_links=True))
held()
for path in targets:
    assert path.resolve()==path and path not in(R,P,H,W,Path('G:/'))
    shutil.rmtree(path);assert not path.exists()
for path in payloads:
    if path.is_dir():shutil.rmtree(path)
    else:path.unlink()
    assert not path.exists()
work=P/'local-owned-qa-v2';assert work.resolve().parent==P.resolve()
for name in('credentials.private.json','accounts-before-cleanup.sqlite3','game-before-cleanup.sqlite3'):
    assert not(work/name).exists(),'Owned local QA worker did not remove temporary snapshots'
removed=[]
for name in('game-before-cleanup.sqlite3-wal','game-before-cleanup.sqlite3-shm'):
    path=work/name
    if path.exists():
        assert path.resolve().parent==work.resolve()and not path.is_symlink()and not path.is_junction()
        if name.endswith('-wal'):assert path.stat().st_size==0
        path.unlink();removed.append(name)
credentials=P/'qa-credentials.private.json'
if credentials.exists():
    assert {v['account_id']for v in read(credentials)}==set(read(P/'qa-cleanup.json')['cleaned_account_ids'])
    credentials.unlink();removed.append(credentials.name)
backup=Path(read(P/'local-installation.json')['backup'])/'game-before.sqlite3'
assert backup.exists()and read(P/'local-store-preservation.json')['ok']
save(P/'owned-cache-cleanup.json',dict(ok=True,removed=rows,credentials_and_sidecars_removed=removed,
    superseded_private_payloads_removed=payload_rows,first_failed_build_small_metadata_retained=True,
    local_QA_temporary_snapshots_already_removed_by_qualified_worker=True,local_recovery_snapshot_retained=str(backup),
    signed_recovery_archive_retained=True,player_database_restore=False))
print(json.dumps(dict(ok=True,removed_caches=len(rows),superseded_private_payloads=len(payload_rows),bytes=sum(r['bytes']for r in rows+payload_rows),local_recovery_backup_retained=True)))
