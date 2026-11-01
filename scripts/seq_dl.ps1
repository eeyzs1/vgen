param()
# Sequential download orchestrator: one file at a time, 4-6 parallel chunks each.
# Priority: torch wheel -> VAE -> diffusion -> text encoder
$ErrorActionPreference = 'Continue'

$items = @(
    @{ Url = 'https://mirrors.aliyun.com/pytorch-wheels/cu130/torch-2.13.0%2Bcu130-cp312-cp312-win_amd64.whl';
       Dest = 'G:\vgen\downloads\wheels\torch-2.13.0+cu130-cp312-cp312-win_amd64.whl';
       Size = [long]1915519202; N = 4 },
    @{ Url = 'https://modelscope.cn/models/Comfy-Org/minimax-H3/resolve/master/vae/minimax_h3_video_vae_int8_convrot.safetensors';
       Dest = 'G:\vgen\models\vae\minimax_h3_video_vae_int8_convrot.safetensors';
       Size = [long]2811065184; N = 4 },
    @{ Url = 'https://modelscope.cn/models/Comfy-Org/minimax-H3/resolve/master/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors';
       Dest = 'G:\vgen\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors';
       Size = [long]20970379616; N = 6 },
    @{ Url = 'https://modelscope.cn/models/Comfy-Org/minimax-H3/resolve/master/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors';
       Dest = 'G:\vgen\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors';
       Size = [long]15687142551; N = 6 }
)

foreach ($it in $items) {
    $name = Split-Path $it.Dest -Leaf
    Write-Output "=== START $name (expect $($it.Size)) ==="
    & G:\vgen\scripts\pd.ps1 -Url $it.Url -Dest $it.Dest -Expected $it.Size -N $it.N
    Write-Output "=== EXIT $name code=$LASTEXITCODE ==="
    if ($LASTEXITCODE -ne 0) { Write-Output "ORCHESTRATOR: continuing to next item" }
}
Write-Output "ALL DOWNLOADS FINISHED"
