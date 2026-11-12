"""Retire this finished publication's stage and two owned scheduled tasks."""
from common import *
import base64

held()
for name in('progress-readback.json','online-installation-acceptance.json','ordinary-entry-open.json','qa-cleanup.json'):
    assert read(P/name)['ok']
assert read(P/'ordinary-entry-open.json')['ordinary_entry_open']
inspection=read(P/'remote-closeout-inspection.json')
assert inspection['compaction']['ok']and not inspection['references']
assert all(row['readback_verified']for row in inspection['compaction']['backups'])
assert read(P/'stage-owner.json')['source_head']==plan['source_head']
ps=r'''$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$root=[IO.Path]::GetFullPath('C:\ElsFriends-staging');$target=[IO.Path]::GetFullPath(STAGE)
if([IO.Path]::GetDirectoryName($target) -ne $root){throw 'Publication stage boundary changed'}
$owner=Get-Content -LiteralPath (Join-Path $target 'stage-owner.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$requirements=Get-Content -LiteralPath (Join-Path $target 'requirements.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if($owner.owner -ne OWNER -or $owner.release -ne RID -or $owner.source_head -ne HEAD -or $requirements.owner -ne OWNER -or $requirements.release -ne RID){throw 'Publication stage owner changed'}
if((Get-FileHash -LiteralPath (Join-Path $target 'requirements.json') -Algorithm SHA256).Hash -ine REQUIREMENTS){throw 'Publication requirements changed'}
$compact=Get-Content -LiteralPath COMPACTION -Encoding UTF8 -Raw | ConvertFrom-Json
if(-not $compact.ok -or @($compact.backups | Where-Object {-not $_.readback_verified}).Count){throw 'QA recovery compression incomplete'}
$entries=@(Get-Item -LiteralPath $target -Force)+@(Get-ChildItem -LiteralPath $target -Force -Recurse)
foreach($parent in @($root,'C:\')){if((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked publication ancestor'}}
if(@($entries | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Linked publication stage'}
if(@(Get-CimInstance Win32_Process | Where-Object {$_.ProcessId -ne $PID -and ($_.ExecutablePath+' '+$_.CommandLine).Replace('/','\').IndexOf($target,[StringComparison]::OrdinalIgnoreCase) -ge 0}).Count){throw 'Stage still referenced by process'}
$taskNames=@('ELS-Achievement-Guild-Banner-Power-Publication-20261108-v1','ELS-Achievement-Guild-Banner-Power-Publication-20261108-v1-compact')
foreach($name in $taskNames){$task=Get-ScheduledTask -TaskName $name;$info=Get-ScheduledTaskInfo -TaskName $name;if($task.State -eq 'Running' -or $info.LastTaskResult -ne 0 -or @($task.Actions).Count -ne 1 -or $task.Actions[0].Execute.Replace('/','\') -ine 'C:\ElsFriends\python\python.exe' -or $task.Actions[0].Arguments.Replace('/','\').IndexOf($target,[StringComparison]::OrdinalIgnoreCase) -lt 0){throw 'Active or changed publication task'}}
$evidence=EVIDENCE
if(Test-Path -LiteralPath $evidence){throw 'Publication record already exists'}
if([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($evidence)) -ne [IO.Path]::GetFullPath($requirements.backup_directory)){throw 'Recovery record boundary changed'}
New-Item -ItemType Directory -Path $evidence | Out-Null
$retained=@('stage-owner.json','requirements.json','control.py','journal.json','journal.jsonl','qa-cleanup-result.json','compact_qa_backups.py','shared_snapshot.py','qa_remote_worker.py','achievement_fixture.py','owned_qa_cleanup.py','game-start-intent.json','game-stop-intent.json','control.stderr')
foreach($name in $retained){
 $source=Join-Path $target $name;$destination=Join-Path $evidence $name
 Copy-Item -LiteralPath $source -Destination $destination
 if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash){throw 'Publication record copy differs'}
}
foreach($name in $taskNames){Unregister-ScheduledTask -TaskName $name -Confirm:$false}
Remove-Item -LiteralPath $target -Recurse -Force
if(Test-Path -LiteralPath $target){throw 'Publication stage remains'}
@{ok=$true;retired_tasks=2;server_stage_removed=$true;permanent_record=$evidence;database_backups_retained=$true;small_record_files=$retained.Count}|ConvertTo-Json -Compress
'''
quote=lambda s:"'"+str(s).replace("'","''")+"'"
backup=read(P/'requirements.json')['backup_directory']
for key,value in(('STAGE',STAGE),('OWNER',OWNER),('RID',RID),('HEAD',plan['source_head']),('REQUIREMENTS',sha(P/'requirements.json')),
    ('COMPACTION','C:/ElsFriends/backups/'+RID+'-qa/compressed-cleanup-backups.json'),('EVIDENCE',backup+'/publication-record')):
    ps=ps.replace(key,quote(value))
(P/'retire-publication-stage.ps1').write_text(ps,'utf8')
answer=remote('import subprocess\np=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-WindowStyle","Hidden","-EncodedCommand",'+repr(base64.b64encode(ps.encode('utf-16le')).decode())+'],capture_output=True,timeout=50);assert not p.returncode,p.stderr.decode("utf8","replace")[-1800:];print(p.stdout.decode("utf-8-sig"))')
save(P/'publication-stage-cleanup.json',answer)
save(P/'QA-backups-compacted.json',inspection['compaction'])
print(json.dumps(answer))
