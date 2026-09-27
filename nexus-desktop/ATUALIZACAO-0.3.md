# Nexus Wolf’s 0.3.0 — etapa 2 e início da etapa 3

## Abrir a versão atualizada

Na pasta Projeto-KibaGames, abra **Abrir Nexus.bat**. **Abrir biblioteca.bat** também encaminha para a versão nova quando há uma distribuição compilada. **Abrir biblioteca antiga.bat** mantém o acesso ao aplicativo Python/MySQL anterior.

O lançador consulta `release/latest.txt`. O executável e suas dependências ficam juntos em uma subpasta de `release/`. Não mova apenas o EXE. Cada compilação cria uma distribuição com versão e data, preservando builds anteriores. Um atalho antigo que aponte para outra cópia do projeto não foi alterado automaticamente. Execute **Atualizar atalho.bat** na pasta principal para apontá-lo à versão nova; uma cópia do atalho anterior fica em `work/shortcut-backups`.

O build recompila a interface React a partir do código atual e compara o SHA-256 de cada arquivo web com a cópia dentro da distribuição Windows. Ele também executa o autoteste com banco temporário próprio antes de atualizar `release/latest.txt`. Assim, uma compilação incompleta não substitui a versão ativa, e app/web não usam interfaces diferentes por um build antigo.

## Etapa 2: serviço local e distribuição

- FastAPI e SQLite são iniciados junto com a interface, na mesma janela, sem terminal ou login MySQL na abertura normal. Ao fechar a janela, o serviço é encerrado.
- Porta local dinâmica, restrita a 127.0.0.1. O React usa a mesma origem. O preview Vite nas portas 1420/4173 usa o serviço de desenvolvimento 8765.
- A distribuição utiliza **Python + pywebview/WebView2 + PyInstaller**, alternativa local prevista no documento arquitetural. O scaffold Tauri continua disponível, mas não é o executável desta entrega. Rust e MSVC não foram instalados. Não há benchmark de RAM que permita prometer redução percentual.
- SQLite em `data/biblioteca`; uma migração concluída em `data/biblioteca-importada` passa a ser selecionada na abertura. Os diretórios permanecem fora da distribuição. Dados criados em ambas as bases não são mesclados automaticamente.
- Perfis e senhas persistem no banco; token fica somente na memória e é revogado no logout. O serviço verifica o proprietário em todas as operações privadas. Detalhes de segurança e migração: [backend/README.md](backend/README.md).
- Imagens JPEG/PNG/WebP são validadas, reorientadas, convertidas em WebP qualidade 85 e recebem miniaturas. Limites de tamanho, pixels e downloads HTTPS são aplicados no serviço.

## Etapa 3: funcionalidades conectadas

- `src/features/library/GameCard.tsx`: cards 3:4, cantos de 16 px, elevação 6 px, zoom 5%, transição 300 ms, foco por teclado, preferência de movimento reduzido, estrela de favorito e troféus.
- `CoverImage.tsx`: IntersectionObserver carrega a imagem quando visível; cancela a transferência e libera a URL de Blob ao sair da área visível/desmontar. A galeria usa miniaturas; o editor usa a imagem maior.
- `LibraryView.tsx`: grade/lista, paginação de 20 registros, busca com debounce de 300 ms, normalização de acentos e combinação com gênero, favoritos por perfil e destaque do jogo com maior progresso válido em andamento. Jogos 0%/100% ficam fora do destaque.
- Coleções com mosaico, criação, renomeação, exclusão com confirmação e vínculo por arrastar uma capa. Excluir uma coleção preserva seus jogos. Também há seleção acessível de coleção no editor.
- `GameEditor.tsx`: nome, plataforma, gênero, status, progresso, ordem, coleção, notas, datas, troféus e capa. Pode importar imagem local, baixar por URL HTTPS ou remover. Calcula percentual de troféus e só concede platina quando total > 0 e obtidos = total.
- Alterações no editor exigem salvar. Sair com alterações pede confirmação. Falha ao carregar um jogo mostra erro e repetição, sem liberar um formulário vazio para sobrescrever dados.
- O cronograma existente é preservado ao salvar. Esta entrega não reconstrói ainda o calendário visual de arrastar dias.

## Migração real: pendência externa

O importador foi implementado e testado com bases isoladas, mas **os dados pessoais ainda não foram importados**. Este ambiente recebeu `PermissionError / WinError 5` ao ler `%LOCALAPPDATA%/NexusPlay/conexao.dat`. Nenhuma tentativa alterou o MySQL original.

Para importar localmente, feche o Nexus e abra `../Importar biblioteca MySQL.bat`. Ele solicita a senha de root no seu terminal, sem exibi-la nem enviá-la ao chat. Para outro usuário, execute `scripts/import-mysql.ps1 -AskPassword -MysqlUser NOME`. O destino precisa estar ausente: uma migração existente não é sobrescrita. Ao terminar, abra novamente o app. Se houver jogos sem proprietário, siga a mensagem do importador e o parâmetro explícito `-OwnerForUnassigned` documentado no backend.

## Testes e limites

- 24 testes backend: autenticação, isolamento de perfis, CRUD, filtros, datas/troféus, imagens, migração preservada, frontend estático e escolha de diretório.
- 4 testes frontend: troféus, preservação do cronograma, validações e parâmetros opcionais da busca. Um parâmetro `undefined` que causava HTTP 422 foi reproduzido e corrigido.
- TypeScript e build Vite validados. Executável real passou no autoteste de health, frontend empacotado e carregamento de pywebview/WinForms. Este autoteste não comprova sozinho a renderização de uma janela WebView2.
- Interface verificada no navegador com perfil e capas sintéticos em `work/ui-test-library`, separados da biblioteca pessoal: login, favorito, editor, troféus e busca sem acentos.
- Os testes emitem um aviso de depreciação do TestClient Starlette/httpx; não houve falha associada.
- Busca automática de capas por nome, calendário avançado e interface completa de avatar/recorte/alteração de senha ainda precisam ser concluídos na nova interface. Os endpoints de conta já existem. O aplicativo antigo permanece disponível enquanto essas funcionalidades são migradas.
- Instalador assinado, integração final Tauri e atualização automática ainda não estão implementados. O código-fonte desta versão é preparado para publicação no GitHub; os binários e dados locais ficam fora do repositório.

## Recompilar

```powershell
pnpm build
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-desktop.txt
.\scripts\build-desktop.ps1
```

`requirements-desktop-lock.txt` registra as versões verificadas. `scripts/setup-backend.ps1` prepara o ambiente do backend. O executável registra erros em `runtime.log` no diretório de dados.
