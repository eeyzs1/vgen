param()
# Music 3 weight downloads: TE -> DiT -> DAV, serial, 6-way chunks, ModelScope
$ErrorActionPreference = 'Continue'

$base = 'https://modelscope.cn/models/Comfy-Org/MiniMax-Music-3/resolve/master/'
$items = @(
    @{ Path = 'text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors'; Size = [long]9196611886; N = 6 },
    @{ Path = 'diffusion_models/minimax_music3_dit_fp16.safetensors'; Size = [long]4914197682; N = 6 },
    @{ Path = 'vae/minimax_music3_dav.safetensors'; Size = [long]216696128; N = 3 }
)

foreach ($it in $items) {
    $leaf = Split-Path $it.Path -Leaf
    $dest = Join-Path 'G:\vgen\models' $it.Path
    Write-Output "=== START $leaf ==="
    & G:\vgen\scripts\pd.ps1 -Url ($base + $it.Path) -Dest $dest -Expected $it.Size -N $it.N
    Write-Output "=== EXIT $leaf code=$LASTEXITCODE ==="
}
Write-Output "MUSIC3 DOWNLOADS FINISHED"
