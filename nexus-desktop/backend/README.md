# Etapa 2 — serviço local e persistência

Implementado em FastAPI + SQLite + Pillow. O serviço escuta **somente `127.0.0.1:8765`**. Não exige um servidor MySQL para novas bibliotecas. MySQL é utilizado exclusivamente como origem da migração.

## Iniciar no Windows

No PowerShell, dentro de `nexus-desktop`:

```powershell
.\scripts\setup-backend.ps1
.\scripts\start-backend.ps1
```

O instalador usa um ambiente `.venv` do projeto, sem modificar as dependências do aplicativo antigo. `requirements-lock.txt` registra as versões exatas usadas na validação (inclui ferramentas de teste). Python 3.12+; o script reconhece a instalação padrão do Python 3.13. Se necessário: `setup-backend.ps1 -PythonExe 'C:\caminho\python.exe'`.

Em outro terminal, execute `pnpm build` e `pnpm preview --port 1420`, ou use `pnpm dev` em um ambiente que permita a preparação de dependências pelo esbuild. A interface acessa somente a API local. Clique em **Escolher meu perfil** para criar um perfil ou selecionar um perfil já salvo e entrar com sua senha. Esta etapa mostra a conexão e as contagens reais. A galeria de jogos será ligada na etapa de cards.

Os scripts não alteram a política de execução do Windows. Se sua máquina bloquear scripts PowerShell, os comandos equivalentes, dentro de `nexus-desktop`, são:

```powershell
# Depois de criar a .venv e instalar as dependências:
cd backend
..\.venv\Scripts\python.exe -m nexus_backend --data-dir ..\data\biblioteca
```

## Onde ficam os dados

O launcher escolhe `data/biblioteca-importada` quando existe uma importação concluída; caso contrário usa `data/biblioteca`. É possível escolher explicitamente com `start-backend.ps1 -DataDir 'C:\caminho\biblioteca'`. Ao executar o módulo sem `--data-dir`, o padrão é `%LOCALAPPDATA%/NexusWolfs`; `NEXUS_DATA_DIR` pode sobrescrever esse padrão.

- `nexus.sqlite3`: perfis, jogos, coleções e metadados de imagens.
- `images/<id>.webp`: imagens processadas; `<id>.thumb.webp`: miniaturas.
- `origem-mysql.sqlite3`: cópia de recuperação dos registros MySQL, criada na importação, incluindo colunas originais e imagens originais sem recompressão.
- `relatorio-migracao.json`: contagens e verificações da importação.

- `backups/nexus-backup-*.zip`: backups criados pela interface (banco, imagens e manifesto com hashes); copie um ZIP para cá para restaurá-lo.

Dados, backups, ambiente Python, downloads de dependências e logs ficam ignorados pelo Git. Copie a pasta de dados inteira com o serviço encerrado para um backup manual consistente, ou use *Backup e recuperação* na interface, que funciona com o aplicativo aberto. SQLite e imagens não são criptografados em disco; use as permissões e a proteção do usuário Windows. Não compartilhe backups ou arquivos da pasta de dados.

## Migração MySQL → SQLite

Encerre as edições no aplicativo antigo durante a cópia. Não é necessário apagá-lo ou desinstalar MySQL.

```powershell
# Na pasta nexus-desktop, reutiliza a configuração DPAPI existente:
.\scripts\import-mysql.ps1

# Se a configuração salva não estiver disponível, pede a senha no terminal:
.\scripts\import-mysql.ps1 -AskPassword -MysqlUser root
```

A senha do MySQL não é salva pelo importador e não deve ser enviada pelo chat. Depois do sucesso, reinicie o backend; ele selecionará a pasta importada. Isso **não mescla** uma biblioteca SQLite nova com a biblioteca importada. A pasta nova continua intacta e pode ser selecionada por `-DataDir`.

Etapas da importação:

1. Abre transação MySQL **somente leitura**, com snapshot consistente.
2. Copia as três tabelas e seus `SHOW CREATE TABLE` para um snapshot SQLite de recuperação. Preserva todas as colunas, inclusive desconhecidas, datas, hashes e bytes das imagens.
3. Cria a nova base em uma pasta temporária ao lado do destino; preserva IDs e hashes PBKDF2 existentes, portanto as senhas de perfil continuam válidas.
4. Importa jogos, notas, cronogramas, favoritos, troféus, datas, ordem e associações. Grupos antigos sem coleção viram coleções do mesmo perfil.
5. Converte imagens para WebP 85 e cria miniaturas; os originais permanecem no snapshot.
6. Confere contagens, `foreign_key_check` e `integrity_check`, grava relatório, fecha todos os arquivos e publica a pasta por renomeação.

Uma pasta de destino existente **nunca é substituída**. Em erro, o destino não é publicado e a pasta `.migrando-*` permanece para diagnóstico. Imagens inválidas, hashes desconhecidos, conflitos de nomes normalizados ou referências inconsistentes interrompem a migração em vez de descartar dados. Jogos antigos sem dono exigem uma decisão explícita: `-OwnerForUnassigned ID` atribui somente jogos sem usuário a um perfil existente. Perfis referenciados e inexistentes não são remapeados automaticamente.

O snapshot não é um dump de todo o servidor MySQL; é a cópia completa das três tabelas do aplicativo. A origem não recebe `INSERT`, `UPDATE`, `DELETE`, `ALTER` ou `DROP`. As mudanças feitas depois no app antigo não sincronizam com SQLite.

## Segurança de perfis

- Hash PBKDF2-HMAC-SHA256 com 600.000 iterações e salt individual de 16 bytes, compatível com o legado; comparação em tempo constante.
- Senhas novas de 8 a 256 caracteres; troca exige senha atual e confirmação.
- Tokens aleatórios com 256 bits; somente o hash é mantido em memória por até 12 horas. Logout revoga a sessão; troca de senha revoga todas as sessões do perfil. Reiniciar o backend exige novo login, exceto em aparelhos lembrados.
- "Lembrar neste aparelho": credencial de 256 bits por aparelho, guardada só como hash SHA-256 na tabela `aparelhos`, rotacionada a cada uso, válida por 90 dias sem uso; sair esquece o aparelho, trocar a senha esquece todos. Por 60 s após a rotação, a credencial anterior ainda abre sessão sem receber credencial nova. O esquema do banco está na versão 6 (migrações incrementais em `database.MIGRATIONS`; a v4 acrescenta a ficha do jogo: lançamento, estúdios, descrição e identificador externo; a v5, ordem manual, "ainda jogando", origem dos troféus, preferências e galeria de avatares; a v6, a ficha completa em JSON validado: requisitos, idiomas, classificação indicativa, tempo de jogo, Metacritic e categorias).
- A interface mantém o token apenas em memória. Ela salva o perfil no SQLite, não a senha nem o token no navegador.
- Até cinco tentativas de autenticação por perfil por minuto.
- Operações de jogos, imagens e coleções sempre verificam o dono. O banco também impede jogos vinculados a uma coleção de outro usuário.
- Perfis (nome, ID e referência do avatar) e miniaturas de avatar são públicos **no serviço local**, para montar o seletor de contas. Jogos e imagens completas exigem autenticação.
- Host e Origin são limitados à aplicação local. Respostas não são armazenadas pelo cache HTTP. O serviço não protege contra outro processo malicioso executado na mesma conta do Windows.

## API

Contrato interativo: `http://127.0.0.1:8765/docs`; JSON: `/openapi.json`. A documentação interativa usa os assets padrão do Swagger; a API e o aplicativo funcionam offline. Autenticação: `Authorization: Bearer <token>`.

| Método e rota | Função |
|---|---|
| GET `/api/saude` | Versão, SQLite e versão do esquema |
| GET/POST `/api/perfis` | Selecionar/criar perfil |
| POST/DELETE `/api/sessao` | Login (com `lembrar` e `aparelho` opcionais) / logout |
| POST `/api/sessao/aparelho` | Entrar com a credencial de um aparelho lembrado; devolve sessão e credencial nova (rotação) |
| GET/DELETE `/api/conta/aparelhos` | Listar / esquecer todos os aparelhos lembrados do perfil |
| DELETE `/api/conta/aparelhos/{id}` | Esquecer um aparelho |
| PUT `/api/perfis/{id}/redefinir-senha` | "Esqueci a senha": senha nova + confirmação, sem a atual; só aceito de 127.0.0.1 (nunca pelo celular/rede), 3 por perfil a cada 5 min; revoga sessões e aparelhos lembrados do perfil e registra o evento |
| GET `/api/conta` | Perfil autenticado |
| GET/PUT `/api/conta/preferencias` | Preferências visuais do perfil (`tema`, `movimento`, `densidade`, `destaque`; só valores aprovados) |
| GET `/api/conta/avatares`, PUT/DELETE `/api/conta/avatares/{posicao}` | Galeria de até 5 fotos do perfil; `PUT /api/conta/avatar` define a ativa (entra na galeria se houver vaga; 409 quando cheia) |
| GET `/api/avatares/busca` | Imagens do Wikimedia Commons (`termo`), com licença e autor; prévia pelo proxy `/api/capas/previa` |
| PUT `/api/jogos/ordem` | Ordem manual da biblioteca (`ids`); `GET /api/jogos?ordenacao=minha|nome|recentes|progresso|colecao` |
| GET `/api/capas/fontes` | Se a IGDB está configurada (`igdb.json` na pasta de dados) e onde fica o arquivo |
| GET `/api/trofeus/fontes` | Estado das fontes oficiais de troféus (Steam Web API, RetroAchievements): vinculada, identificação e arquivo; a chave nunca é devolvida |
| PUT/DELETE `/api/trofeus/fontes/{fonte}` | Vincular (chave + SteamID64/usuário, com consulta de teste) ou desvincular; só de 127.0.0.1 |
| GET `/api/trofeus/{fonte}/jogos` | Jogos da conta vinculada (`modo` = recentes ou possuidos) com prévia, tempo, conquistas e o jogo já ligado na biblioteca |
| POST `/api/trofeus/{fonte}/importar` | Cria jogos a partir de `ids` listados pela fonte (ficha, capa, tempo e conquistas; sem tocar dados pessoais); duplicatas ignoradas |
| POST `/api/trofeus/sincronizar` | Atualiza obtidos/total dos jogos ligados às fontes vinculadas (`jogo_id` opcional); falhas relatadas por jogo, valores nunca zerados |
| PUT `/api/conta/senha` | Senha atual, nova senha e confirmação |
| PUT `/api/conta/avatar` | Vincular imagem de avatar ou remover vínculo com `null` |
| GET `/api/resumo` | Contagens do perfil |
| GET/POST `/api/jogos` | Listagem paginada/cadastro |
| GET/PATCH/DELETE `/api/jogos/{id}` | Detalhar, editar campos ou excluir |
| GET `/api/destaques` | Até 20 jogos em andamento, progresso decrescente |
| GET/POST `/api/colecoes` | Coleções com contagens e até quatro IDs de capa para mosaico |
| PUT/DELETE `/api/colecoes/{id}` | Renomear/alterar capa ou excluir sem apagar jogos |
| POST `/api/imagens` | Upload binário de JPEG/PNG/WebP, conversão e miniatura |
| POST `/api/imagens/url` | Baixar imagem HTTPS direta e converter |
| GET `/api/imagens/{id}?miniatura=true` | Imagem do perfil autenticado |
| GET `/api/perfis/{id}/avatar` | Miniatura para seleção de perfil |
| GET `/api/acesso-rede` | Estado do acesso pela rede local: ativo, porta, endereços, certificado, erro |
| PUT `/api/acesso-rede` | Liga/desliga o listener HTTPS (`ativo`, `porta` opcional); só aceito de 127.0.0.1 |
| GET `/api/acesso-rede/ca.crt` | Certificado público da autoridade local, para instalar no celular |
| GET `/api/atualizacao` | Versão, build, modo (instalado/portátil), canal, atualização disponível/preparada, versão anterior |
| POST `/api/atualizacao/verificar|preparar|aplicar|reverter` | Atualizador do aplicativo instalado (hash + autoteste; aplicar/reverter fecham o app) |
| GET/POST `/api/manutencao/backups` | Listar / criar backup (ZIP com banco, imagens e manifesto); só de 127.0.0.1 |
| GET/DELETE `/api/manutencao/backups/{nome}` | Baixar / excluir um backup |
| POST `/api/manutencao/backups/{nome}/restaurar` | Validar, fazer backup de segurança e restaurar; revoga todas as sessões |
| GET `/api/manutencao/integridade` | `integrity_check`, `foreign_key_check`, contagens e esquema |
| GET `/api/manutencao/orfas`, POST `/orfas/limpar` | Contar / apagar imagens sem uso (com backup de segurança antes) |
| GET `/api/capas/busca` | Candidatos de capa pelo nome (`nome`, `fonte` = todas, steam ou wikipedia); até 20 por minuto por perfil |
| GET `/api/capas/previa` | Prévia de um candidato, buscada pelo serviço; só hosts de imagem das fontes |

## Capas pelo nome

`covers.py` consulta a loja Steam e a Wikipedia (pt, depois en) sem chave de API, usando `images.fetch` com lista fechada de hosts, e devolve candidatos com imagem, prévia e página de origem; só URLs dos hosts de imagem de cada fonte são aceitas. A interface baixa a escolha por `POST /api/imagens/url`. Detalhes, limitações e atribuição: [ATUALIZACAO-0.3.md](../ATUALIZACAO-0.3.md).

## Acesso pela rede local

Desligado por padrão. Ao ligar, o mesmo aplicativo passa a escutar também em HTTPS (`0.0.0.0`, porta escolhida, padrão 8443) com um certificado emitido por uma autoridade criada na pasta de dados (`certificados/nexus-ca.crt`; chaves privadas ao lado, nunca servidas). A preferência fica em `acesso-rede.json` e é reaplicada na abertura por `desktop.py` e por `python -m nexus_backend`. O cabeçalho `Host` só é aceito para loopback e para os endereços anunciados pelo listener; `Origin` precisa coincidir com a própria origem (`http` ou `https`). A geração dos certificados usa `cryptography`. Detalhes de uso: [ATUALIZACAO-0.3.md](../ATUALIZACAO-0.3.md).

`GET /api/jogos` aceita `busca`, `genero`, `favorito`, `colecao_id`, `pagina` e `limite` (1–100, padrão 40). Texto é normalizado sem acentos e diferenças de caixa; `%` e `_` são literais, não curingas. Busca e gênero se combinam com **E**. Listas não carregam BLOBs, notas ou cronogramas. Índices atendem usuário, nome, favoritos, progresso e coleção. O debounce de 300 ms será ligado à busca visual na etapa de cards.

`PATCH` mescla somente os campos enviados, validando o objeto final dentro de transação. Datas usam ISO `YYYY-MM-DD`. Cronograma é `{ "2026-09-07": "single", "2026-09-08": "range" }`. Datas futuras continuam armazenadas como dias e são diferenciadas visualmente pelo calendário. Troféus respeitam `0 ≤ obtidos ≤ total ≤ 1.000.000`; `0/0` retorna 0% e **não** significa platinado. Destaques excluem 0%, 100%, pausados, abandonados, concluídos e jogos na fila.

Para arrastar um jogo para uma coleção, o futuro componente chama `PATCH /api/jogos/{id}` com `{ "colecao_id": ID, "ordem": 1 }`. Remover o vínculo usa `null`. Confirmar a exclusão da coleção será responsabilidade da UI antes de chamar a API.

## Imagens e memória

- Upload é o arquivo binário no corpo (não multipart), com `?tipo=capa|avatar|colecao`.
- Recorte opcional: `x`, `y`, `largura`, `altura` em pixels **após orientação EXIF**, compatível com `croppedAreaPixels` do react-easy-crop. O frontend de recorte será feito em etapa posterior.
- Limites: 10 MB, 20 megapixels, apenas imagens estáticas. No máximo duas conversões simultâneas.
- WebP qualidade 85; capas até 900×1200 preservando proporção, avatares quadrados até 512×512 e coleções até 900×900. Miniaturas de capa até 240×320; outras até 160×160. Sem ampliação desnecessária; metadados removidos.
- Arquivos são escritos atomicamente e deduplicados por conteúdo, perfil e tipo. Remover a referência não apaga imediatamente o arquivo, evitando perda de imagens compartilhadas. A limpeza de imagens sem uso fica em *Backup e recuperação*, sempre com backup de segurança antes.
- Downloads aceitam HTTPS público direto; não aceitam páginas de resultados de busca, rede privada, credenciais na URL ou portas alternativas. DNS é validado, IP é fixado na conexão, hostname é mantido no TLS e cada redirecionamento é revalidado. Tamanho, tempo de leitura e redirecionamentos são limitados.
- A API prepara paginação e miniaturas; a virtualização e o ciclo de vida de URLs de Blob serão implementados nos cards. Nenhuma redução de 80% em disco ou meta de RAM foi presumida: isso depende das imagens e será medido.

## Código

`database.py`: esquema versionado, WAL, transações e índices. `security.py`: senhas, sessões e limites de tentativas. `models.py`: validações. `service.py`: operações de domínio. `images.py`: download, recorte, conversão e armazenamento. `api.py`: HTTP e autorização. `migration.py`: cópia e validação MySQL. `src/services/api.ts`: cliente TypeScript para a próxima etapa. `BackendProvider.tsx` e `BackendPanel.tsx`: conexão real de perfis e resumo na interface.

## Verificar

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ..
pnpm build
```

Os testes usam diretórios temporários, imagens sintéticas e registros de migração sintéticos. Cobrem isolamento, persistência após reinício, credenciais, invalidação de sessões, regras de jogos/troféus, exclusão de coleções, busca/paginação, limites de upload, EXIF/recorte, bloqueio de URL privada e redirecionamento, preservação de backup e rejeição de migração parcial.

Resultado em 24/10/2026: **65 testes aprovados** no back-end (inclui `test_metadata.py` e `test_platforms.py`) e 27 no front-end; o parágrafo abaixo descreve a primeira entrega da etapa 2 (então 22 testes). `pip check` sem dependências quebradas, scripts PowerShell com sintaxe válida e build TypeScript/Vite aprovado. O TestClient emitiu um aviso de depreciação sobre o transporte httpx, sem falhas nos testes. A interface confirmou “Serviço local conectado”, formulário de perfil com rolagem interna e ausência de overflow horizontal em viewport de 390 px. Não foram criados perfis fictícios na biblioteca do usuário. Um download HTTPS real do logo público do Python também foi convertido com sucesso em WebP; esse único arquivo não representa uma estimativa de economia para capas de jogos.

## Limitações da entrega

O MySQL real **não foi migrado nesta sessão**: o ambiente recusou a leitura de `%LOCALAPPDATA%/NexusPlay/conexao.dat`. A migração precisa ser executada localmente pelos comandos acima. Não houve alteração da origem nem cópia de senhas para arquivos do projeto.

FastAPI/Pillow e dependências estão instalados na `.venv` local. Rust/C++ não são necessários para testar este backend e não foram instalados. O empacotamento do Python como sidecar e a inicialização/encerramento automáticos pelo executável Tauri ainda não estão implementados; nesta fase o backend e o preview são iniciados separadamente. Cards, formulários completos de jogos, cropper visual e migração guiada pertencem às próximas etapas.

Referências: [FastAPI](https://fastapi.tiangolo.com/), [Pillow — segurança de imagens](https://pillow.readthedocs.io/en/stable/handbook/security.html), [Tauri — sidecars](https://v2.tauri.app/develop/sidecar/).
