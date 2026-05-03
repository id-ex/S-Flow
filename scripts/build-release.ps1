param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputDir = "release",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$configPath = Join-Path $ProjectRoot "src\core\config.py"
$configText = Get-Content -LiteralPath $configPath -Raw
if ($configText -notmatch 'APP_VERSION\s*=\s*"([^"]+)"') {
    throw "APP_VERSION not found in $configPath"
}

$version = $Matches[1]
$releaseDir = Join-Path $ProjectRoot $OutputDir
$versionDir = Join-Path $releaseDir "v$version"

if ($Clean) {
    Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "dist" -Recurse -Force -ErrorAction SilentlyContinue
}

pyinstaller S-Flow.spec

$exePath = Join-Path $ProjectRoot "dist\S-Flow.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Build failed: $exePath not found"
}

New-Item -ItemType Directory -Path $versionDir -Force | Out-Null

$releaseExePath = Join-Path $versionDir "S-Flow.exe"
Copy-Item -LiteralPath $exePath -Destination $releaseExePath -Force

$hash = (Get-FileHash -LiteralPath $releaseExePath -Algorithm SHA256).Hash.ToLowerInvariant()
$size = (Get-Item -LiteralPath $releaseExePath).Length

$manifest = [ordered]@{
    version = $version
    url = "S-Flow.exe"
    sha256 = $hash
    size = $size
    notes = "S-Flow v$version"
}

$manifestPath = Join-Path $versionDir "update.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "Built S-Flow v$version"
Write-Host "EXE: $releaseExePath"
Write-Host "Manifest: $manifestPath"
Write-Host "SHA256: $hash"
