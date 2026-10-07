# Lighthouse installer for Windows (ADR 0013). Read it before you run it:
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/ris3abh/Lighthouse/main/install.ps1 | iex"
#
# It installs uv (Astral's Python tool manager) if you don't have it, installs Lighthouse as a uv tool
# on Python 3.12, then starts Lighthouse. It makes no other change to your machine.
#
#   $env:LIGHTHOUSE_GC_SPEC = "<wheel file or URL>"   install this instead of the latest release
#   $env:LIGHTHOUSE_GC_NO_RUN = "1"                   install only; don't start Lighthouse
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = 'ris3abh/Lighthouse'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv (https://docs.astral.sh/uv/) ...'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$HOME\.local\bin;$env:Path"
}

$spec = $env:LIGHTHOUSE_GC_SPEC
if (-not $spec) {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
    $wheel = $release.assets | Where-Object { $_.name -like '*.whl' } | Select-Object -First 1
    if (-not $wheel) { throw "No Lighthouse release found at https://github.com/$repo/releases" }
    $spec = $wheel.browser_download_url
}

Write-Host "Installing Lighthouse from $spec ..."
uv tool install --force --python 3.12 $spec  # uv says if its tool folder isn't on your PATH
if ($LASTEXITCODE -ne 0) { throw 'uv tool install failed (see above).' }

if ($env:LIGHTHOUSE_GC_NO_RUN -eq '1') {
    Write-Host 'Installed. Start Lighthouse any time with: lighthouse-gc'
} else {
    Write-Host "Starting Lighthouse (Ctrl+C stops it; run 'lighthouse-gc' to start it again) ..."
    & (Join-Path (uv tool dir --bin) 'lighthouse-gc.exe')
}
