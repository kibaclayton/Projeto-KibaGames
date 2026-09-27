param([string]$PythonExe = '')
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
if (-not $PythonExe) {
    $installedPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (Test-Path -LiteralPath $installedPython) { $PythonExe = $installedPython }
    else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw 'Python nao encontrado. Informe -PythonExe com o caminho do Python 3.12 ou superior.' }
        $PythonExe = $pythonCommand.Source
    }
}
$venvDir = Join-Path $projectDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente Python.' }
}
& $venvPython -m pip install -r (Join-Path $projectDir 'backend\requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar as dependencias. Verifique a conexao com o PyPI.' }
Write-Host 'Dependencias instaladas. Execute scripts\start-backend.ps1.'
