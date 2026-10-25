param([string]$PnpmCommand = 'pnpm', [switch]$SemInstalador)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
$repoDir = Split-Path $projectDir -Parent
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
Push-Location $projectDir
try {
    & $PnpmCommand build
    if ($LASTEXITCODE -ne 0) { throw 'A interface web nao compilou. A versao anterior foi mantida.' }
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $projectDir 'work\pyinstaller-cache'
    $frontendData = (Join-Path $projectDir 'dist') + ';frontend'
    $updaterData = (Join-Path $projectDir 'scripts\atualizar.ps1') + ';.'
    $appIcon = Join-Path $projectDir 'src-tauri\icons\icon.ico'
    $version = (Get-Content package.json -Raw | ConvertFrom-Json).version
    $buildId = Get-Date -Format 'yyyyMMdd-HHmmss'
    $buildName = "NexusWolfs-$version-$buildId"
    & $pythonExe -m PyInstaller --noconfirm --onedir --windowed --name $buildName --distpath release --workpath work/pyinstaller --specpath work --paths backend --add-data $frontendData --add-data $updaterData --icon $appIcon --collect-all webview --collect-all clr_loader --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on backend/desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o executavel.' }
    $buildDir = Join-Path $projectDir "release\$buildName"
    $relativeExe = "release\$buildName\$buildName.exe"
    # versao.json acompanha o executavel: o aplicativo mostra o build e o atualizador compara com o canal.
    $versionJson = @{ versao = $version; build = $buildId; exe = 'NexusWolfs.exe'; gerado = (Get-Date).ToString('s') } | ConvertTo-Json
    $utf8 = New-Object System.Text.UTF8Encoding($false)  # sem BOM: o aplicativo le estes JSON com json.loads
    [System.IO.File]::WriteAllText((Join-Path $buildDir 'versao.json'), $versionJson, $utf8)
    $packagedFrontend = Join-Path $buildDir '_internal\frontend'
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

    # Pacote de atualizacao e instalador usam um nome fixo de executavel (NexusWolfs.exe), para atalhos e atualizador estaveis.
    $stageDir = Join-Path $projectDir "release\stage-$buildId"
    if (Test-Path -LiteralPath $stageDir) { Remove-Item -LiteralPath $stageDir -Recurse -Force }
    Copy-Item -LiteralPath $buildDir -Destination $stageDir -Recurse
    Rename-Item -LiteralPath (Join-Path $stageDir "$buildName.exe") -NewName 'NexusWolfs.exe'
    $zipPath = Join-Path $projectDir "release\$buildName.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $zipPath -CompressionLevel Optimal
    $zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLower()
    $manifest = [ordered]@{ versao = $version; build = $buildId; arquivo = (Split-Path $zipPath -Leaf); sha256 = $zipHash; tamanho = (Get-Item -LiteralPath $zipPath).Length; data = (Get-Date).ToString('s'); notas = '' } | ConvertTo-Json
    [System.IO.File]::WriteAllText((Join-Path $projectDir 'release\atualizacao.json'), $manifest, $utf8)
    Write-Host "Pacote de atualizacao: $zipPath"

    if (-not $SemInstalador) {
        $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if ($iscc) {
            $projectData = Join-Path $projectDir 'data\biblioteca'
            $channel = Join-Path $projectDir 'release'
            & $iscc /Qp "/DAppVersion=$version" "/DBuildId=$buildId" "/DSourceDir=$stageDir" "/DOutputDir=$(Join-Path $projectDir 'release')" "/DProjectData=$projectData" "/DChannel=$channel" (Join-Path $PSScriptRoot 'instalador.iss')
            if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar o instalador.' }
            Write-Host "Instalador: release\NexusWolfs-Setup-$version-$buildId.exe"
        } else {
            Write-Host 'Inno Setup 6 nao encontrado; instalador nao gerado (winget install JRSoftware.InnoSetup).'
        }
    }
    Remove-Item -LiteralPath $stageDir -Recurse -Force
} finally { Pop-Location }
