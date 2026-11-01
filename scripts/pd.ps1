param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$Dest,
    [Parameter(Mandatory=$true)][long]$Expected,
    [int]$N = 8,
    [string]$Sha256 = ''
)
$ErrorActionPreference = 'Stop'
$extra = @()
if ($Sha256) { $extra = @('--sha256',$Sha256) }
& python "$PSScriptRoot\studio_download.py" --url $Url --dest $Dest --expected $Expected --workers $N @extra
if ($LASTEXITCODE -ne 0) { throw 'Download failed; partial data retained for inspection/resume' }
