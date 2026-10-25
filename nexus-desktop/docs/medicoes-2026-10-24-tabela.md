| Aplicativo | Até API (s) | Até janela (s) | CPU na abertura (s) | Processos | RAM working set (MB) | RAM privada (MB) | CPU ocioso (%) |
|---|---|---|---|---|---|---|---|
| Nexus Wolfs (instalado) | 1,05 | 0,22 | 1,81 | 7 | 454,3 | 262,7 | 0,39 |
| Biblioteca antiga (Tkinter/MySQL) |  | 0,91 | 0,42 | 2 | 73 | 38,6 | 0 |
| mysqld (serviço do app antigo, sempre ligado) | - | - | - | 2 | 442,8 | 670,5 | - |

| Espaço em disco | MB |
|---|---|
| Nexus: aplicativo instalado | 63,8 |
| Nexus: biblioteca (banco + imagens + backups + webview) | 48,8 |
| Nexus: só banco e imagens | 0,8 |
| Antigo: código do aplicativo | 0,1 |
| Antigo: Python 3.13 + pacotes | 227,4 |
| Antigo: MySQL Server (programa) | 576,2 |
| Antigo: MySQL dados (biblioteca_gamer) | sem acesso |
| Antigo: MySQL dados (tudo) | sem acesso |
