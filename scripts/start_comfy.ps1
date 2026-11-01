param([int]$Port = 8188, [string]$Config = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$cfgArgs = @()
if ($Config) { $cfgArgs = @('--config', $Config) }
$cfg = (& python "$PSScriptRoot\studio_settings.py" @cfgArgs | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
$uri = [uri]$cfg.server
if ($PSBoundParameters.ContainsKey('Port') -and $Port -ne $uri.Port) { throw 'Set the server port in configuration so all clients agree' }
if ($uri.Host -notin @('localhost','127.0.0.1')) { throw 'Managed service must use localhost' }
$state = $cfg.state
New-Item -ItemType Directory -Force -Path $state | Out-Null
$record = Join-Path $state 'service.json'
try { Invoke-RestMethod "$($cfg.server)/system_stats" -TimeoutSec 3 | Out-Null; Write-Output 'Service already available; ownership unchanged'; exit 0 } catch {}
if (Test-Path -LiteralPath $record) { throw 'Ownership record exists; inspect or stop owned service first' }
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$servicePid = & python "$PSScriptRoot\studio_service.py" @cfgArgs
if ($LASTEXITCODE -ne 0) { throw 'Detached launch failed' }
$proc = Get-Process -Id ([int]$servicePid)
@{pid=$proc.Id; started=$proc.StartTime.ToUniversalTime().ToString('o'); executable=$cfg.python; comfy=$cfg.comfy} | ConvertTo-Json | Set-Content -LiteralPath $record -Encoding ASCII
for ($i=0; $i -lt 60; $i++) {
    if ($proc.HasExited) { throw 'ComfyUI exited; inspect .studio logs' }
    try { Invoke-RestMethod "$($cfg.server)/system_stats" -TimeoutSec 2 | Out-Null; Write-Output "Owned service ready: $($proc.Id)"; exit 0 } catch {}
    Start-Sleep -Seconds 2
}
throw 'Startup timed out; ownership record retained for inspection'
