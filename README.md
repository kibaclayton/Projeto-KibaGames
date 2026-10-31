# Projeto-KibaGames — NEXUS PLAY LIBRARY

## Nova interface: Nexus Wolf’s

A versão **0.3.0** está em [nexus-desktop](nexus-desktop/README.md): React, TypeScript, Tailwind, FastAPI e SQLite, distribuídos em uma janela Windows com pywebview/WebView2. Aplicativo e navegador usam a mesma interface React. O scaffold Tauri está preservado para evolução futura.

A [etapa 2](nexus-desktop/backend/README.md) implementa serviço local, perfis, WebP e importador MySQL que preserva a origem. O início da etapa 3 adiciona cards, grade/lista, favoritos, coleções, busca, editor com troféus e o calendário de sessões de jogo no modal de edição. A etapa 4 permite abrir a biblioteca no celular pela rede Wi-Fi de casa, por HTTPS com certificado próprio e desligado por padrão; os dados continuam somente no computador. A etapa 5 traz as configurações da conta: foto de perfil circular com recorte e alteração de senha. A etapa 6 busca a capa sozinha pelo nome do jogo, na Steam e na Wikipedia, sem chave de API. A etapa 7 permite lembrar o perfil num aparelho, com credencial rotacionada e revogável, para o celular não pedir a senha a cada abertura. A etapa 8 traz backup e restauração pela interface, verificação de integridade e limpeza de imagens sem uso, sempre com backup de segurança antes de qualquer alteração. A etapa 9 gera um instalador do Windows (`release/NexusWolfs-Setup-*.exe`, por usuário, sem administrador) e um atualizador que verifica, baixa, confere o hash, executa o autoteste e só aplica com confirmação, guardando a versão anterior para reverter. A etapa 10 transforma a busca de capas em busca de jogos: ao tocar num resultado (Steam ou Wikipedia/Wikidata, sem chave), a capa e a ficha do mesmo jogo preenchem os campos vazios do formulário, sem gravar nada até "Salvar jogo" e sem tocar progresso, notas, troféus ou datas pessoais. As melhorias de 25/10/2026 trazem busca para PlayStation, Xbox e Nintendo (IGDB opcional com chave local), galeria de até cinco fotos por perfil com busca no Wikimedia Commons, total de troféus sugerido pela Steam, "Ainda estou jogando" com dias de jornada e dias jogados, Favoritos com painel amplo, Biblioteca e Coleções separadas, ordem manual dos jogos e a página Personalizar visual. Na mesma noite entraram os troféus por fontes oficiais com chave pessoal guardada só no computador (Steam Web API e RetroAchievements: importar jogos da conta e sincronizar obtidos/total; PlayStation, Xbox, Nintendo e Epic ficam manuais por não terem API oficial) e a ficha completa ao escolher um jogo (requisitos mínimos e recomendados, idiomas, classificação indicativa ClassInd/PEGI/ESRB, Metacritic, categorias e, com IGDB, tempo de jogo). Em 30/10/2026 chegaram o visualizador de troféus por jogo (cada conquista com ícone, data e raridade) e as capas da Steam em lote para jogos sem capa. Veja [entrega e pendências](nexus-desktop/ATUALIZACAO-0.3.md), incluindo as funcionalidades antigas ainda não migradas.

### Preparar a versão nova no Windows

Instale Node.js 22.18 ou superior, pnpm 11.19, Python 3.12/3.13 de 64 bits e o runtime Microsoft Edge WebView2. Dentro de `nexus-desktop`:

```powershell
pnpm install --frozen-lockfile
.\scripts\setup-backend.ps1
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-desktop.txt
.\scripts\build-desktop.ps1
```

Na pasta principal, abra **Abrir Nexus.bat** (modo portátil) ou instale com `nexus-desktop/release/NexusWolfs-Setup-*.exe` (modo instalado, com atualização automática; a biblioteca portátil é importada por cópia na primeira abertura). O build recompila a versão web, compara todos os arquivos empacotados e testa o EXE antes de torná-lo a versão atual. **Atualizar atalho.bat** direciona o atalho antigo da área de trabalho para o lançador novo e guarda uma cópia do atalho anterior. Distribuições, ambientes Python, credenciais e dados pessoais não são publicados no GitHub.

Para importar uma biblioteca MySQL existente, feche o Nexus e abra **Importar biblioteca MySQL.bat**. A importação dos dados pessoais precisa ser executada localmente e não está concluída só por baixar este código.

## Aplicativo anterior (aposentado em 24/10/2026)

A versão original em Python/Tkinter/MySQL foi aposentada depois que a sua biblioteca (2 perfis, 7 jogos, 3 coleções e capas) foi importada para o Nexus. Os arquivos dela ficaram em [`legado/`](legado/) apenas como referência e recuperação: `app.py`, `biblioteca.py`, `calendario.py`, `capas.py`, `contas.py`, `conexao_segura.py`, `requirements.txt`, os `.bat` antigos, `DOCUMENTACAO.md` e `LEIA-ME.txt`. O MySQL Server e o Python 3.13 não são mais necessários para o Nexus; a desinstalação deles é uma decisão à parte. O importador (`nexus-desktop/scripts/import-mysql.ps1`) continua funcionando e procura `conexao_segura.py` também em `legado/`.
