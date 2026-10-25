<#
.SYNOPSIS
  Mede tempo de abertura, RAM, CPU e espaço em disco do Nexus Wolf's instalado e do aplicativo antigo (Python/Tkinter/MySQL).

.DESCRIPTION
  Para cada aplicativo, abre o programa N vezes (padrão 3), espera ficar pronto, aguarda um período ocioso e amostra a
  árvore de processos (o Nexus inclui os processos msedgewebview2 que ele cria; o app antigo é o python.exe, e o mysqld é
  listado à parte como dependência). Fecha o aplicativo entre as rodadas. Não altera bancos nem dados: só lê contadores do
  sistema e tamanhos de pastas. Grava um JSON com as amostras e um Markdown com medianas.

  Pré-requisitos: Nexus instalado (NexusWolfs.exe em %LOCALAPPDATA%\Programs\Nexus Wolfs), app antigo abrível por
  "Abrir biblioteca antiga.bat" (Python 3.13 + MySQL84 em execução). Feche os dois aplicativos antes de rodar.

.EXAMPLE
  .\scripts\medir-desempenho.ps1 -Rodadas 3 -Ocioso 20
#>
param(
  [int]$Rodadas = 3,
  [int]$Ocioso = 20,
  [int]$Espera = 90,
  [string]$Saida = (Join-Path $PSScriptRoot '..\docs'),
  [switch]$SemAntigo
)
$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$nexusExe = Join-Path $env:LOCALAPPDATA 'Programs\Nexus Wolfs\NexusWolfs.exe'
$nexusDados = Join-Path $env:LOCALAPPDATA 'NexusWolfs'
$pythonAntigo = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
$cores = [int](Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors

function Arvore([int]$Processo) {
  # PID informado mais todos os descendentes (WebView2 cria processos netos).
  $todos = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name
  $fila = New-Object System.Collections.Generic.Queue[int]; $fila.Enqueue($Processo)
  $vistos = @{}
  while ($fila.Count -gt 0) {
    $atual = $fila.Dequeue()
    if ($vistos.ContainsKey($atual)) { continue }
    $vistos[$atual] = $true
    foreach ($f in $todos | Where-Object { $_.ParentProcessId -eq $atual }) { $fila.Enqueue([int]$f.ProcessId) }
  }
  return @($vistos.Keys)
}

function Amostra([int[]]$Pids) {
  $ws = 0; $priv = 0; $cpu = 0.0; $n = 0
  foreach ($id in $Pids) {
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($p) { $ws += $p.WorkingSet64; $priv += $p.PrivateMemorySize64; $cpu += $p.TotalProcessorTime.TotalSeconds; $n++ }
  }
  return [pscustomobject]@{ processos = $n; ws_mb = [math]::Round($ws / 1MB, 1); privado_mb = [math]::Round($priv / 1MB, 1); cpu_s = [math]::Round($cpu, 2) }
}

function Esperar-Janela([System.Diagnostics.Process]$P, [int]$Limite) {
  $t = [Diagnostics.Stopwatch]::StartNew()
  while ($t.Elapsed.TotalSeconds -lt $Limite) {
    $P.Refresh()
    if ($P.HasExited) { return $null }
    if ($P.MainWindowHandle -ne 0) { return [math]::Round($t.Elapsed.TotalSeconds, 2) }
    Start-Sleep -Milliseconds 100
  }
  return $null
}

function Esperar-Api([string]$Url, [int]$Limite) {
  $t = [Diagnostics.Stopwatch]::StartNew()
  while ($t.Elapsed.TotalSeconds -lt $Limite) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2; if ($r.StatusCode -eq 200) { return [math]::Round($t.Elapsed.TotalSeconds, 2) } } catch {}
    Start-Sleep -Milliseconds 100
  }
  return $null
}

function Fechar([System.Diagnostics.Process]$P) {
  $arvore = Arvore $P.Id
  try { $null = $P.CloseMainWindow() } catch {}
  if (-not $P.WaitForExit(15000)) { foreach ($id in $arvore) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } }
  Start-Sleep -Seconds 3
}

function Medir-App([string]$Nome, [scriptblock]$Abrir, [string]$Api) {
  $resultados = @()
  for ($r = 1; $r -le $Rodadas; $r++) {
    Write-Host ("[{0}] rodada {1}/{2}" -f $Nome, $r, $Rodadas)
    $inicio = Get-Date
    $p = & $Abrir
    $tApi = $null
    if ($Api) { $tApi = Esperar-Api $Api $Espera }
    $tJanela = Esperar-Janela $p $Espera
    if ($null -eq $tJanela -and $null -eq $tApi) { Fechar $p; throw "$Nome não abriu em $Espera s." }
    $pronto = Amostra (Arvore $p.Id)
    Start-Sleep -Seconds $Ocioso
    $depois = Amostra (Arvore $p.Id)
    $cpuOcioso = [math]::Round(([double]($depois.cpu_s) - [double]($pronto.cpu_s)) / [double]$Ocioso / [double]$cores * 100, 2)
    $resultados += [pscustomobject]@{
      app = $Nome; rodada = $r; inicio = $inicio.ToString('s'); ate_api_s = $tApi; ate_janela_s = $tJanela
      cpu_abertura_s = $pronto.cpu_s; processos = $depois.processos; ws_mb = $depois.ws_mb; privado_mb = $depois.privado_mb
      cpu_ocioso_s = [math]::Round($depois.cpu_s - $pronto.cpu_s, 2); cpu_ocioso_pct = $cpuOcioso
    }
    Fechar $p
  }
  return $resultados
}

function Tamanho([string]$Caminho) {
  try {
    if (-not (Test-Path -LiteralPath $Caminho)) { return $null }
    $item = Get-Item -LiteralPath $Caminho
    if (-not $item.PSIsContainer) { return $item.Length }
    return (Get-ChildItem -LiteralPath $Caminho -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  } catch { return $null }
}

function Mediana($Valores) {
  $v = @($Valores | Where-Object { $null -ne $_ } | Sort-Object)
  if ($v.Count -eq 0) { return $null }
  if ($v.Count % 2 -eq 1) { return $v[[int][math]::Floor($v.Count / 2)] }
  return [math]::Round(($v[$v.Count / 2 - 1] + $v[$v.Count / 2]) / 2, 2)
}

# --- Medições ---------------------------------------------------------------------------------------------------------
if (Get-Process NexusWolfs -ErrorAction SilentlyContinue) { throw 'Feche o Nexus antes de medir.' }
if (Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*app.py*' }) { throw 'Feche a biblioteca antiga antes de medir.' }
$amostras = @()
$amostras += Medir-App 'Nexus Wolfs (instalado)' { Start-Process -FilePath $nexusExe -WorkingDirectory (Split-Path $nexusExe) -PassThru } 'http://127.0.0.1:48765/api/saude'
if (-not $SemAntigo) {
  $amostras += Medir-App 'Biblioteca antiga (Tkinter/MySQL)' { Start-Process -FilePath $pythonAntigo -ArgumentList 'app.py' -WorkingDirectory $raiz -PassThru } ''
}
$mysqld = @(Get-Process mysqld -ErrorAction SilentlyContinue)
$dependencia = if ($mysqld.Count) { Amostra ($mysqld | ForEach-Object { $_.Id }) } else { $null }

$disco = [ordered]@{
  'Nexus: aplicativo instalado' = Tamanho (Split-Path $nexusExe)
  'Nexus: biblioteca (banco + imagens + backups + webview)' = Tamanho $nexusDados
  'Nexus: só banco e imagens' = (Tamanho (Join-Path $nexusDados 'nexus.sqlite3')) + (Tamanho (Join-Path $nexusDados 'images'))
  'Antigo: código do aplicativo' = ((Get-ChildItem -LiteralPath $raiz -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.py', '.bat', '.txt' } | Measure-Object Length -Sum).Sum)
  'Antigo: Python 3.13 + pacotes' = Tamanho (Split-Path $pythonAntigo)
  'Antigo: MySQL Server (programa)' = Tamanho 'C:\Program Files\MySQL\MySQL Server 8.4'
  'Antigo: MySQL dados (biblioteca_gamer)' = Tamanho 'C:\ProgramData\MySQL\MySQL Server 8.4\Data\biblioteca_gamer'
  'Antigo: MySQL dados (tudo)' = Tamanho 'C:\ProgramData\MySQL\MySQL Server 8.4\Data'
}

# --- Saída ------------------------------------------------------------------------------------------------------------
$carimbo = Get-Date -Format 'yyyy-MM-dd'
$so = Get-CimInstance Win32_OperatingSystem
$json = [ordered]@{ gerado = (Get-Date).ToString('s'); maquina = @{ cores = $cores; ram_gb = [math]::Round([double]($so.TotalVisibleMemorySize) / 1MB, 1); windows = $so.Caption; build_nexus = (Get-Content (Join-Path (Split-Path $nexusExe) 'versao.json') -Raw | ConvertFrom-Json).build }
  parametros = @{ rodadas = $Rodadas; ocioso_s = $Ocioso }; amostras = $amostras; mysqld = $dependencia; disco_bytes = $disco }
New-Item -ItemType Directory -Force $Saida | Out-Null
[IO.File]::WriteAllText((Join-Path $Saida "medicoes-$carimbo.json"), ($json | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding $false))

$linhas = @("| Aplicativo | Até API (s) | Até janela (s) | CPU na abertura (s) | Processos | RAM working set (MB) | RAM privada (MB) | CPU ocioso (%) |", "|---|---|---|---|---|---|---|---|")
foreach ($grupo in $amostras | Group-Object app) {
  $a = $grupo.Group
  $linhas += ("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |" -f $grupo.Name, (Mediana $a.ate_api_s), (Mediana $a.ate_janela_s), (Mediana $a.cpu_abertura_s), (Mediana $a.processos), (Mediana $a.ws_mb), (Mediana $a.privado_mb), (Mediana $a.cpu_ocioso_pct))
}
if ($dependencia) { $linhas += ("| mysqld (serviço do app antigo, sempre ligado) | - | - | - | {0} | {1} | {2} | - |" -f $dependencia.processos, $dependencia.ws_mb, $dependencia.privado_mb) }
$linhas += ""; $linhas += "| Espaço em disco | MB |"; $linhas += "|---|---|"
foreach ($k in $disco.Keys) { $v = $disco[$k]; $linhas += ("| {0} | {1} |" -f $k, $(if ($null -ne $v) { [math]::Round($v / 1MB, 1) } else { 'sem acesso' })) }
$md = ($linhas -join "`n") + "`n"
[IO.File]::WriteAllText((Join-Path $Saida "medicoes-$carimbo-tabela.md"), $md, (New-Object Text.UTF8Encoding $false))
Write-Host $md
Write-Host ("Amostras em {0}" -f (Join-Path $Saida "medicoes-$carimbo.json"))
