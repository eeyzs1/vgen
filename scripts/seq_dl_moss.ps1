param()
# MOSS SFX big weight downloads: transformer -> TE1 -> TE2 -> VAE, serial, 6-way chunks, hf-mirror
$ErrorActionPreference = 'Continue'

$base = 'https://hf-mirror.com/OpenMOSS-Team/MOSS-SoundEffect-v2.0/resolve/main/'
$root = 'G:\vgen\models\moss-sfx\MOSS-SoundEffect-v2.0'
$items = @(
    @{ Path = 'transformer/diffusion_pytorch_model.safetensors'; Size = [long]5664274560; N = 6 },
    @{ Path = 'text_encoder/model-00001-of-00002.safetensors'; Size = [long]3441185608; N = 6 },
    @{ Path = 'text_encoder/model-00002-of-00002.safetensors'; Size = [long]622329984; N = 4 },
    @{ Path = 'vae/vae_128d_48k.pth'; Size = [long]1486465965; N = 4 }
)

foreach ($it in $items) {
    $leaf = Split-Path $it.Path -Leaf
    Write-Output "=== START $leaf ==="
    & G:\vgen\scripts\pd.ps1 -Url ($base + $it.Path) -Dest (Join-Path $root ($it.Path -replace '/','\')) -Expected $it.Size -N $it.N
    Write-Output "=== EXIT $leaf code=$LASTEXITCODE ==="
}
Write-Output "MOSS SFX DOWNLOADS FINISHED"
