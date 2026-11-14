# Build from canonical modules so the test app cannot silently use stale copies.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('pw-vision-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot 'tools/vision_app/app.yaml') -Destination $stage
New-Item -ItemType Directory -Path (Join-Path $stage 'python') | Out-Null
foreach ($file in @('main.py','requirements.txt')) {
    Copy-Item -LiteralPath (Join-Path $repoRoot "tools/vision_app/python/$file") -Destination (Join-Path $stage 'python')
}
foreach ($module in @('vision.py','clothing.py','shutter.py','contracts.py','api.py')) {
    Copy-Item -LiteralPath (Join-Path $repoRoot "device/python/$module") -Destination (Join-Path $stage 'python')
}
$archive = Join-Path $repoRoot 'vision-check.zip'
if (Test-Path (Join-Path $repoRoot 'device/python/models')) {
    Copy-Item -LiteralPath (Join-Path $repoRoot 'device/python/models') -Destination (Join-Path $stage 'python') -Recurse
}
Compress-Archive -Path (Join-Path $stage 'app.yaml'),(Join-Path $stage 'python') -DestinationPath $archive -Force
Write-Output "Built $archive from canonical production modules. Temporary staging: $stage"
