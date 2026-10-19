param([string]$Root='C:\ElsFriends',[string]$SourceAddress)
# Run on the prepared server directory. Does not edit any website or DNF path.
$ErrorActionPreference='Stop'
$basePath=[IO.Path]::GetFullPath($Root).TrimEnd('\')
if ($basePath -ne 'C:\ElsFriends') { throw 'This deployment is confined to C:\ElsFriends' }
$python=Join-Path $basePath 'python\python.exe'
$config=Join-Path $basePath 'config\friends-server.toml'
if (-not (Test-Path -LiteralPath $python)) { throw 'Verified isolated runtime missing' }
foreach ($file in @('state\friends\server-cert.pem','state\friends\server-key.pem','state\friends\accounts.sqlite3')) {
    if (-not (Test-Path -LiteralPath (Join-Path $basePath $file))) { throw ('Missing provisioned identity: '+$file) }
}
$privateDir=Join-Path $basePath 'state'
# Directory inheritance flags are not file permissions. Apply each type
# separately; /T with directory-only flags can leave files without access.
foreach ($directory in @($privateDir)+@(Get-ChildItem -LiteralPath $privateDir -Directory -Recurse | Select-Object -ExpandProperty FullName)) {
    & icacls.exe $directory /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Private state directory ACL failed' }
}
foreach ($file in Get-ChildItem -LiteralPath $privateDir -File -Recurse) {
    & icacls.exe $file.FullName /inheritance:r /grant:r '*S-1-5-32-544:F' '*S-1-5-18:F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Private state file ACL failed' }
}
& $python -m els_server --config $config --check
if ($LASTEXITCODE -ne 0) { throw 'Server preflight failed' }
$portRule='ELS-Friends-TLS'
if (-not (Get-NetFirewallRule -Name $portRule -ErrorAction SilentlyContinue)) {
    $scope=if ($SourceAddress) {$SourceAddress} else {'LocalSubnet'}
    $null=New-NetFirewallRule -Name $portRule -DisplayName 'ELS friends authenticated TLS' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 19400 -RemoteAddress $scope -Program $python
}
$runDir=Join-Path $basePath 'run'
$null=New-Item -ItemType Directory -Path $runDir -Force
$stopFile=Join-Path $runDir 'server.stop'
if (Test-Path -LiteralPath $stopFile) { Remove-Item -LiteralPath $stopFile }
$taskName='ELS-Friends-Server'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Existing ELS task detected; stop and update it explicitly' }
$action=New-ScheduledTaskAction -Execute $python -Argument ('-m els_server --config "'+$config+'" --stop-file "'+$stopFile+'"') -WorkingDirectory $basePath
$trigger=New-ScheduledTaskTrigger -AtStartup
$principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings=New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
$null=Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings
Start-ScheduledTask -TaskName $taskName
$backupAction=New-ScheduledTaskAction -Execute $python -Argument ('"'+(Join-Path $basePath 'tools\backup_friends_server.py')+'" --config "'+$config+'" --destination "'+(Join-Path $basePath 'backups')+'"') -WorkingDirectory $basePath
$backupTrigger=New-ScheduledTaskTrigger -Daily -At '04:00'
$null=Register-ScheduledTask -TaskName 'ELS-Friends-Backup' -Action $backupAction -Trigger $backupTrigger -Principal $principal
Get-ScheduledTask -TaskName 'ELS-Friends-*' | Select-Object TaskName,State
