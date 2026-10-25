param(
    [Parameter(Mandatory = $true)][string]$Instalacao,
    [string]$Nova = '',
    [int]$ProcessId = 0,
    [string]$Exe = 'NexusWolfs.exe',
    [string]$Log = '',
    [switch]$Reverter
)
# Troca a pasta instalada do Nexus pela versao preparada (ou devolve a anterior) depois que o aplicativo fecha.
# Roda fora do aplicativo, a partir de uma copia em %TEMP%, porque a pasta instalada e renomeada durante a troca.
$ErrorActionPreference = 'Stop'
function Registrar($texto) {
    if ($Log) { Add-Content -LiteralPath $Log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $texto) -Encoding UTF8 }
}
function Renomear($origem, $destino) {
    # Arquivos recem-fechados podem ficar presos por alguns instantes; tenta de novo antes de desistir.
    for ($tentativa = 1; $tentativa -le 20; $tentativa++) {
        try { Move-Item -LiteralPath $origem -Destination $destino -ErrorAction Stop; return } catch { Start-Sleep -Milliseconds 500 }
    }
    Move-Item -LiteralPath $origem -Destination $destino -ErrorAction Stop
}
$anterior = "$Instalacao.anterior"
try {
    # ($PID e uma variavel automatica do PowerShell; por isso o parametro se chama ProcessId.)
    if ($ProcessId -gt 0) {
        $limite = (Get-Date).AddSeconds(90)
        while ((Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) -and (Get-Date) -lt $limite) { Start-Sleep -Milliseconds 300 }
    }
    Start-Sleep -Seconds 1
    if ($Reverter) {
        if (-not (Test-Path -LiteralPath "$anterior\$Exe")) { throw 'Nao ha versao anterior guardada.' }
        $descartada = "$Instalacao.descartada"
        if (Test-Path -LiteralPath $descartada) { Remove-Item -LiteralPath $descartada -Recurse -Force }
        Renomear $Instalacao $descartada
        Renomear $anterior $Instalacao
        Remove-Item -LiteralPath $descartada -Recurse -Force -ErrorAction SilentlyContinue
        Registrar "Revertido para a versao anterior em $Instalacao"
    } else {
        if (-not (Test-Path -LiteralPath "$Nova\$Exe")) { throw "Versao preparada nao encontrada em $Nova" }
        if (Test-Path -LiteralPath $anterior) { Remove-Item -LiteralPath $anterior -Recurse -Force }
        Renomear $Instalacao $anterior
        try {
            Renomear $Nova $Instalacao
        } catch {
            Registrar "Falha ao colocar a versao nova; devolvendo a anterior: $_"
            Renomear $anterior $Instalacao
            throw
        }
        Registrar "Atualizado: $Instalacao (anterior guardada em $anterior)"
    }
    Start-Process -FilePath "$Instalacao\$Exe" -WorkingDirectory $Instalacao
} catch {
    Registrar "ERRO: $_"
    if (Test-Path -LiteralPath "$Instalacao\$Exe") { Start-Process -FilePath "$Instalacao\$Exe" -WorkingDirectory $Instalacao }
    exit 1
}
