param(
    [Parameter(Mandatory=$true)][string]$Events,
    [int]$Variants = 3,
    [int]$Steps = 50,
    [string]$Batch = 'batch_auto',
    [int]$BaseSeed = 1000,
    [int]$Width = 1216,
    [int]$Height = 832,
    [switch]$FreeGpu,
    [string]$Config = ''
)
# Consumer entrypoint: ensure ComfyUI is running, then generate event illustrations.
#   gen.ps1 -Events dog_alert,false_beacon        (uses G:\vgen\prompts\<id>.txt + IAOD style anchor)
#   gen.ps1 -Events my_asset -Variants 2 -Batch proj_x -FreeGpu
# For raw one-off prompts / other projects' styles, call run_batch.py directly (see README).
$ErrorActionPreference = 'Stop'
$cfgArgs = @()
if ($Config) { $cfgArgs = @('--config',$Config) }
$cfg = (& python "$PSScriptRoot\studio_settings.py" @cfgArgs | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
$py = $cfg.python
& "$PSScriptRoot\start_comfy.ps1" -Config $Config
if (-not $?) { throw 'Service startup failed' }

$extra = @()
if ($Config) { $extra += @('--config',$Config) }
if ($FreeGpu) { $extra += '--free-gpu' }
& $py "$PSScriptRoot\run_batch.py" --events $Events --variants $Variants --steps $Steps `
    --batch $Batch --base-seed $BaseSeed --width $Width --height $Height @extra
exit $LASTEXITCODE
