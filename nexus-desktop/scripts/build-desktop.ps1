param([string]$PnpmCommand = 'pnpm')
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
Push-Location $projectDir
try {
    & $PnpmCommand build
    if ($LASTEXITCODE -ne 0) { throw 'A interface web nao compilou. A versao anterior foi mantida.' }
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $projectDir 'work\pyinstaller-cache'
    $frontendData = (Join-Path $projectDir 'dist') + ';frontend'
    $appIcon = Join-Path $projectDir 'src-tauri\icons\icon.ico'
    $buildName = 'NexusWolfs-' + (Get-Content package.json -Raw | ConvertFrom-Json).version + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    & $pythonExe -m PyInstaller --noconfirm --onedir --windowed --name $buildName --distpath release --workpath work/pyinstaller --specpath work --paths backend --add-data $frontendData --icon $appIcon --collect-all webview --collect-all clr_loader --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on backend/desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o executavel.' }
    $relativeExe = "release\$buildName\$buildName.exe"
    $packagedFrontend = Join-Path $projectDir "release\$buildName\_internal\frontend"
    $sourceFrontend = Join-Path $projectDir 'dist'
    foreach ($sourceFile in Get-ChildItem -LiteralPath $sourceFrontend -File -Recurse) {
        $relativeFile = $sourceFile.FullName.Substring($sourceFrontend.Length + 1)
        $packagedFile = Join-Path $packagedFrontend $relativeFile
        if (-not (Test-Path -LiteralPath $packagedFile) -or
            (Get-FileHash -LiteralPath $sourceFile.FullName).Hash -ne (Get-FileHash -LiteralPath $packagedFile).Hash) {
            throw "A interface empacotada difere da web: $relativeFile"
        }
    }
    $reportPath = Join-Path $projectDir "work\$buildName-smoke.json"
    $testDataPath = Join-Path $projectDir "work\$buildName-smoke-data"
    $smokeArguments = @('--self-test', ('"' + $reportPath + '"'), '--data-dir', ('"' + $testDataPath + '"'))
    $smoke = Start-Process -FilePath (Join-Path $projectDir $relativeExe) -ArgumentList $smokeArguments -PassThru -Wait -WindowStyle Hidden
    if ($smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath)) { throw 'O autoteste do executavel falhou. A versao anterior foi mantida.' }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($report.status -ne 'ok' -or -not $report.frontend -or -not $report.winforms) { throw 'O executavel nao passou na verificacao de abertura.' }
    Set-Content -LiteralPath (Join-Path $projectDir 'release\latest.txt') -Value $relativeExe -Encoding ascii
    Write-Host "Aplicativo atualizado em $relativeExe."
} finally { Pop-Location }
