$ErrorActionPreference = 'Stop'
$sdkRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'mem0'
$demoPath = Join-Path $PSScriptRoot 'demo.py'
if (-not (Test-Path (Join-Path $sdkRoot '.venv\Scripts\hatch.exe'))) {
    throw "Mem0 SDK environment was not found at $sdkRoot. See SETUP.md."
}
Push-Location $sdkRoot
try {
    & .\.venv\Scripts\hatch.exe run local:python $demoPath
    if ($LASTEXITCODE -ne 0) { throw 'Demo failed. See the message above.' }
} finally {
    Pop-Location
}
