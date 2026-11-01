param()
# Round 2 orchestrator: TE then DiT from ModelScope (serial, 6-way each)
$ErrorActionPreference = 'Continue'

$items = @(
    @{ Url = 'https://modelscope.cn/models/Comfy-Org/minimax-H3/resolve/master/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors';
       Dest = 'G:\vgen\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors';
       Size = [long]15687142551; N = 6 },
    @{ Url = 'https://modelscope.cn/models/Comfy-Org/minimax-H3/resolve/master/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors';
       Dest = 'G:\vgen\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors';
       Size = [long]20970379616; N = 6 }
)

foreach ($it in $items) {
    $name = Split-Path $it.Dest -Leaf
    Write-Output "=== START $name ==="
    & G:\vgen\scripts\pd.ps1 -Url $it.Url -Dest $it.Dest -Expected $it.Size -N $it.N
    Write-Output "=== EXIT $name code=$LASTEXITCODE ==="
}
Write-Output "ALL MODEL DOWNLOADS FINISHED"
