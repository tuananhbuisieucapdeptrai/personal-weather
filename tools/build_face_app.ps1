# Package M2.1 without changing the production Python entry point.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('pw-face-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage,(Join-Path $stage 'sketch'),(Join-Path $stage 'python') | Out-Null
@"
name: Personal Weather Face Check
description: LED matrix and buzzer acceptance sequence with live sensor monitoring.
ports: []
bricks: []
"@ | Set-Content (Join-Path $stage 'app.yaml') -Encoding utf8
foreach ($file in @('sketch.ino','sketch.yaml','faces.h')) {
 Copy-Item -LiteralPath (Join-Path $repoRoot "device/sketch/$file") -Destination (Join-Path $stage 'sketch')
}
Copy-Item -LiteralPath (Join-Path $repoRoot 'tools/face_test.py') -Destination (Join-Path $stage 'python/main.py')
foreach ($file in @('bridge_io.py','contracts.py')) {
 Copy-Item -LiteralPath (Join-Path $repoRoot "device/python/$file") -Destination (Join-Path $stage 'python')
}
Compress-Archive -Path (Join-Path $stage 'app.yaml'),(Join-Path $stage 'python'),(Join-Path $stage 'sketch') -DestinationPath (Join-Path $repoRoot 'face-check.zip') -Force
Write-Output 'Built face-check.zip'
