$ErrorActionPreference = 'Stop'
$projectDir = Split-Path $PSScriptRoot -Parent
$repoDir = Split-Path $projectDir -Parent
$launcher = Join-Path $repoDir 'Abrir Nexus.bat'
if (-not (Test-Path -LiteralPath (Join-Path $projectDir 'release\latest.txt'))) { throw 'Compile o aplicativo antes de atualizar o atalho.' }
$desktopDir = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopDir 'Minha Biblioteca de Jogos.lnk'
$backupDir = Join-Path $projectDir 'work\shortcut-backups'
if (Test-Path -LiteralPath $shortcutPath) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Copy-Item -LiteralPath $shortcutPath -Destination (Join-Path $backupDir ((Get-Date -Format 'yyyyMMdd-HHmmss') + '.lnk'))
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $repoDir
$shortcut.Description = 'Nexus Wolfs - biblioteca de jogos atualizada'
$shortcut.IconLocation = (Join-Path $projectDir 'src-tauri\icons\icon.ico') + ',0'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Host 'Atalho atualizado. Ele agora abre a mesma interface React da versao web.'
