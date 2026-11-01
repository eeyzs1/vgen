param([string]$Config = '')
$ErrorActionPreference = 'Stop'
$extra = @()
if ($Config) { $extra = @('--config',$Config) }
& python "$PSScriptRoot\studio_verify.py" @extra
if ($LASTEXITCODE -ne 0) { throw 'Model verification failed' }
