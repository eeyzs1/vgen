param([string]$Config = '')
# Explicit activation only; never called by generation runners.
$ErrorActionPreference = 'Stop'
$extra = @()
if ($Config) { $extra = @('--config',$Config) }
$cfg = (& python "$PSScriptRoot\studio_settings.py" @extra | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
$base = 'https://modelscope.cn/models/Comfy-Org/minimax-H3/resolve/master/'
$items = @(
    @{ Path='vae/minimax_h3_audio_vae_fp32.safetensors'; Size=[long]605254808; Hash='8e505d95dd1561d47abd43d4238fd40d9bb1ae9e1470e4cbaa778d76ae4db48' },
    @{ Path='loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors'; Size=[long]1956193000; Hash='8eba292f83532580787c3d8dd2a4f7635ee51dffc3ebf484ef848fda5e322518' }
)
$sums = Join-Path $cfg.models 'SHA256SUMS'
foreach ($item in $items) {
    $line = "$($item.Hash)  $($item.Path)"
    $existing = @(Get-Content -LiteralPath $sums | Where-Object { ($_ -split '\s+',2)[1] -eq $item.Path })
    if ($existing.Count -gt 0 -and $existing[0] -ne $line) { throw 'Existing hash manifest conflicts with activation recipe' }
    $dest = Join-Path $cfg.models $item.Path
    & "$PSScriptRoot\pd.ps1" -Url ($base + $item.Path) -Dest $dest -Expected $item.Size -N 4 -Sha256 $item.Hash
    if (-not $?) { throw "Download failed: $($item.Path)" }
    if ($existing.Count -eq 0) { Add-Content -LiteralPath $sums -Value $line -Encoding ASCII }
}
& "$PSScriptRoot\verify_models.ps1" -Config $Config
if (-not $?) { throw 'Model verification failed' }
Write-Output 'VIDEO DEPENDENCIES VERIFIED. Live generation and quality acceptance remain separate.'
