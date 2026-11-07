param([ValidateSet('select','local','online')][string]$Mode='select')
$ErrorActionPreference='Stop'
$workspace=Split-Path -Parent $PSScriptRoot
$current=Get-Content -LiteralPath (Join-Path $workspace 'releases\launchers\current.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$exe=[IO.Path]::GetFullPath($current.path)
if((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $current.sha256){throw '正式启动器摘要不符。'}
$arguments=@('--local-root',('"'+$workspace+'"'))
if($Mode -eq 'local'){$arguments=@('--local')+$arguments}
if($Mode -eq 'online'){$arguments=@('--online')+$arguments}
Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -ArgumentList ($arguments -join ' ') -WindowStyle Normal
