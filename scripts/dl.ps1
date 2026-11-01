param([string]$Url, [string]$Dest, [long]$Expected)
# Single-stream resumable download with retry loop until size matches expected
$ErrorActionPreference = 'Continue'
$dir = Split-Path -Path $Dest -Parent
if ($dir) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
for ($i = 1; $i -le 40; $i++) {
  & curl.exe -L --fail --retry 5 --retry-delay 5 -C - --connect-timeout 30 --speed-time 60 --speed-limit 10240 -o $Dest $Url 2>&1 | Out-Null
  $sz = (Get-Item $Dest -ErrorAction SilentlyContinue).Length
  if ($sz -eq $Expected) { Write-Output "DONE $Dest $sz"; exit 0 }
  Write-Output ("attempt {0} incomplete: {1} / {2}, retrying..." -f $i, $sz, $Expected)
  Start-Sleep -Seconds 5
}
Write-Output "FAILED $Dest"
exit 1
