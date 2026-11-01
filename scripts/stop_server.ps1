param([string]$Config = '')
$ErrorActionPreference = 'Stop'
$cfgArgs = @()
if ($Config) { $cfgArgs = @('--config',$Config) }
$cfg = (& python "$PSScriptRoot\studio_settings.py" @cfgArgs | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
$record = Join-Path $cfg.state 'service.json'
if (-not (Test-Path -LiteralPath $record)) { Write-Output 'No owned service; shared processes left running'; exit 0 }
$owner = Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
$proc = Get-Process -Id $owner.pid -ErrorAction SilentlyContinue
if ($proc) {
    $identity = Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.pid)"
    $recordedStart = ([datetime]$owner.started).ToUniversalTime()
    if ($proc.StartTime.ToUniversalTime().Ticks -ne $recordedStart.Ticks -or $identity.ExecutablePath -ne $owner.executable -or $identity.CommandLine -notmatch 'main\.py') { throw 'Process identity mismatch; refusing termination' }
    # taskkill traverses only this verified service process tree.
    & taskkill.exe /PID $owner.pid /T /F
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop owned service tree' }
}
Remove-Item -LiteralPath $record -Force
Write-Output 'Owned service stopped'
