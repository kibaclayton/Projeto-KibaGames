param([switch]$AskPassword, [string]$MysqlUser = 'root', [int]$OwnerForUnassigned = 0)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Execute scripts\setup-backend.ps1 primeiro.' }
$destination = Join-Path $projectDir 'data\biblioteca-importada'
$migrationArgs = @('-X', 'utf8', '-m', 'nexus_backend.migration', '--destination', $destination)
if ($AskPassword) { $migrationArgs += @('--mysql-user', $MysqlUser) }
else { $migrationArgs += '--saved-connection' }
if ($OwnerForUnassigned -gt 0) { $migrationArgs += @('--owner-for-unassigned', "$OwnerForUnassigned") }
Push-Location (Join-Path $projectDir 'backend')
try {
    & $pythonExe @migrationArgs
    if ($LASTEXITCODE -ne 0) { throw 'A importacao nao foi concluida. A origem MySQL permanece intacta.' }
    Write-Host 'Importacao concluida. Reinicie o backend para usar a biblioteca importada.'
} finally { Pop-Location }
