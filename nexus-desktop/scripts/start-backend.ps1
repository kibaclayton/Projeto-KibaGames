param([string]$DataDir = '')
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Execute scripts\setup-backend.ps1 para instalar o ambiente Python deste projeto.'
}
if (-not $DataDir) {
    $importedDir = Join-Path $projectDir 'data\biblioteca-importada'
    $DataDir = if (Test-Path -LiteralPath (Join-Path $importedDir 'nexus.sqlite3')) { $importedDir } else { Join-Path $projectDir 'data\biblioteca' }
}
Push-Location (Join-Path $projectDir 'backend')
try {
    Write-Host 'Nexus: servico local em http://127.0.0.1:8765. Ctrl+C encerra o servico.'
    & $pythonExe -X utf8 -m nexus_backend --data-dir $DataDir
    if ($LASTEXITCODE -ne 0) { throw 'O servico foi encerrado com erro.' }
} finally { Pop-Location }
