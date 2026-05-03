param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ReleaseDir = "release",
    [string]$Repo = "id-ex/S-Flow",
    [string]$Version = "",
    [string]$Notes = "",
    [switch]$Build,
    [switch]$Clean,
    [switch]$Draft
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$configPath = Join-Path $ProjectRoot "src\core\config.py"
$configText = Get-Content -LiteralPath $configPath -Raw
if ($configText -notmatch 'APP_VERSION\s*=\s*"([^"]+)"') {
    throw "APP_VERSION not found in $configPath"
}

$configVersion = $Matches[1]
$version = if ($Version) { $Version.TrimStart("v") } else { $configVersion }
$tag = "v$version"
$versionDir = Join-Path (Join-Path $ProjectRoot $ReleaseDir) $tag

if ($Build -and $version -ne $configVersion) {
    throw "Cannot build version $version because APP_VERSION is $configVersion"
}

if ($Build -or -not (Test-Path -LiteralPath (Join-Path $versionDir "S-Flow.exe"))) {
    $buildArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "build-release.ps1"),
        "-ProjectRoot", $ProjectRoot,
        "-OutputDir", $ReleaseDir
    )
    if ($Clean) {
        $buildArgs += "-Clean"
    }
    & powershell @buildArgs
}

$exePath = Join-Path $versionDir "S-Flow.exe"
$manifestPath = Join-Path $versionDir "update.json"

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Release exe not found: $exePath"
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Update manifest not found: $manifestPath"
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI 'gh' is not installed or not in PATH"
}

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $existingRelease = & gh release view $tag --repo $Repo 2>$null
    $releaseViewExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

if ($releaseViewExitCode -eq 0) {
    throw "Release $tag already exists in $Repo"
}

$notesText = if ($Notes) { $Notes } else { "S-Flow $tag" }
$notesPath = Join-Path $versionDir "release_notes.md"
$notesText | Set-Content -LiteralPath $notesPath -Encoding UTF8

$args = @(
    "release", "create", $tag,
    $exePath,
    $manifestPath,
    "--repo", $Repo,
    "--title", "S-Flow $tag",
    "--notes-file", $notesPath
)

if ($Draft) {
    $args += "--draft"
}

& gh @args
if ($LASTEXITCODE -ne 0) {
    throw "gh release create failed"
}

Write-Host "Published $tag to $Repo"
Write-Host "Manifest URL:"
Write-Host "https://github.com/$Repo/releases/latest/download/update.json"
