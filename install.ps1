# Area O1 installer for Windows (ADR 0013). Read it before you run it:
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/ris3abh/areao1/main/install.ps1 | iex"
#
# It installs uv (Astral's Python tool manager) if you don't have it, installs Area O1 as a uv tool
# on Python 3.12, then starts Area O1. It makes no other change to your machine.
#
#   $env:AREAO1_SPEC = "<wheel file or URL>"   install this instead of the latest release
#   $env:AREAO1_NO_RUN = "1"                   install only; don't start Area O1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = 'ris3abh/areao1'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing uv (https://docs.astral.sh/uv/) ...'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$HOME\.local\bin;$env:Path"
}

$spec = $env:AREAO1_SPEC
if (-not $spec) {
    $release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
    $wheel = $release.assets | Where-Object { $_.name -like '*.whl' } | Select-Object -First 1
    if (-not $wheel) { throw "No Area O1 release found at https://github.com/$repo/releases" }
    $spec = $wheel.browser_download_url
}

Write-Host "Installing Area O1 from $spec ..."
uv tool install --force --python 3.12 $spec  # uv says if its tool folder isn't on your PATH
if ($LASTEXITCODE -ne 0) { throw 'uv tool install failed (see above).' }

if ($env:AREAO1_NO_RUN -eq '1') {
    Write-Host 'Installed. Start Area O1 any time with: areao1'
} else {
    Write-Host "Starting Area O1 (Ctrl+C stops it; run 'areao1' to start it again) ..."
    & (Join-Path (uv tool dir --bin) 'areao1.exe')
}
