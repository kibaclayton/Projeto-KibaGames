# NEXUS PLAY LIBRARY

## Documentação funcional e técnica — 07/09/2026

**Base:** revisão dos arquivos atuais e do histórico de desenvolvimento. Este documento registra o que foi feito, como funciona e quais verificações foram realizadas. Não representa uma certificação de que todas as telas e integrações passaram em testes no computador do usuário.

## Sumário

1. Visão geral e histórico
2. Ambiente e arquivos
3. Arquitetura e tecnologias
4. Conexão e perfis
5. Galeria e destaques
6. Coleções
7. Editor, favoritos e troféus
8. Calendário
9. Capas e imagens
10. Conta e segurança
11. Banco de dados
12. Gravação e migrações
13. Testes e evidências
14. Limitações
15. Operação e backup
16. Manutenção do código
17. Glossário

## 1. Visão geral e histórico

O programa começou como uma biblioteca pessoal para cadastrar jogos, guardar suas capas e acompanhar manualmente o percentual jogado. Evoluiu para um aplicativo de desktop Windows com perfis separados, coleções, favoritos, calendário, notas e troféus.

O aplicativo organiza informações. Não executa os jogos e não detecta automaticamente o que acontece dentro deles.

| Etapa | O que foi feito | Como foi feito |
|---|---|---|
| Preparação | Instalação do Python | Orientação para instalar Python 3.13.15 de 64 bits. O comando `python` apontava para a Microsoft Store; passou-se a usar o caminho completo do executável. |
| Conector | Comunicação Python–MySQL | Instalação de `mysql-connector-python`. A captura enviada confirmou a versão 26.7.0. |
| Banco | Instalação do MySQL Server 8.4.11 | Orientação pelo MySQL Configurator, serviço MySQL84 e conexão local. |
| Teste inicial | Conexão com o banco | Script simples executado pelo usuário, que informou sucesso. |
| Primeira biblioteca | Nome, plataforma, capa e progresso | Interface Tkinter e tabela MySQL com busca, cadastro, edição e exclusão. |
| Datas | Início e término | Campos de data com validação de formato e ordem cronológica. |
| Atalho | Abertura pela Área de Trabalho | Arquivo `.lnk` apontando para o iniciador `.bat`. |
| Capas online | Busca pelo nome | API da Wikipedia, prévia e escolha do resultado. |
| Séries | Grupos e ordem numérica | Campos para organizar franquias em sequência. |
| NEXUS | Tema escuro e contas | Menu lateral, destaque, cores neon e autenticação por perfil. |
| Editor moderno | Duas colunas | Calendário, status avançado e notas, preservando os campos anteriores. |
| Favoritos | Estrela e filtro | Campo booleano por jogo e perfil. |
| Perfis visuais | Seleção por cartões | Nome salvo; ao escolher, pede somente a senha do perfil. |
| Conexão protegida | Evitar redigitar MySQL | Implementação da DPAPI do Windows para guardar a conexão. |
| Galeria | Capas sem textos sobrepostos | Detalhes acessíveis ao clicar no jogo. |
| Coleções | Pastas visuais e arraste | Migração dos grupos, mosaicos, vínculo, renomeação e exclusão. |
| Troféus e perfil | Contagem, avatar e senha | Percentual dos troféus, upload de foto e alteração de senha com validação da atual. |
| Documentação | Registro do trabalho | Inspeção dos arquivos sem alterar os jogos ou o programa. |

As instruções antigas sobre grupos, login MySQL em toda abertura e cartões com barras descrevem versões anteriores. As próximas seções descrevem o estado atual do código.

## 2. Ambiente e arquivos

### Ambiente identificado no histórico

- Windows de 64 bits.
- Python 3.13.15 instalado para o usuário.
- MySQL Server 8.4.11.
- Serviço configurado como `MySQL84`, com início junto ao Windows.
- Porta local 3306.
- Foi orientado desmarcar a abertura de portas no firewall para acesso pela rede; essa configuração não foi auditada novamente.

### Caminhos importantes

| Item | Localização |
|---|---|
| Aplicativo revisado | `[caminho local omitido]` |
| ZIP produzido | `[caminho local omitido]` |
| Atalho criado no histórico | `[caminho local omitido]` |
| Python usado pelo iniciador | `%LocalAppData%\Programs\Python\Python313\python.exe` |
| Conexão protegida, quando salva | `%LOCALAPPDATA%\NexusPlay\conexao.dat` |
| Scripts de testes | `[caminho local omitido]` |
| Pasta atual da conversa | `[caminho local omitido]` |
| Esta documentação | Subpasta `outputs` da pasta GAMES atual. |

**A mudança da pasta da conversa não transferiu automaticamente o aplicativo, o banco ou o destino do atalho.** Os arquivos revisados continuam na pasta original acima.

### O iniciador

`Abrir biblioteca.bat`:

1. Muda o diretório corrente para sua própria pasta.
2. Localiza o Python 3.13 no caminho padrão do usuário.
3. Testa as importações do conector e do Pillow.
4. Se faltarem componentes, instala `requirements.txt` com pip.
5. Executa `app.py`.
6. Mantém o terminal aberto em caso de erro.

Não foi criado um executável independente `.exe`. O programa depende do Python instalado. O iniciador testa importações; não compara todas as versões já instaladas com as faixas declaradas.

## 3. Arquitetura e tecnologias

| Tecnologia | Responsabilidade |
|---|---|
| Python | Regras, eventos, comunicação com banco e processamento dos dados. |
| Tkinter / ttk | Janelas, modais, campos, botões, grades e barras. |
| Canvas do Tkinter | Calendário desenhado, cartões de perfil e superfícies de imagem. |
| MySQL | Persistência de jogos, contas, coleções, imagens e cronogramas. |
| MySQL Connector/Python | Comunicação Python–MySQL. |
| Pillow | Conversão, redimensionamento, recorte de avatar e mosaicos. |
| urllib e json | Consulta de capas e interpretação das respostas. |
| threading e queue | Busca de capas fora da execução principal da interface. |
| hashlib, hmac e secrets | Hash e verificação das senhas dos perfis. |
| ctypes e DPAPI | Proteção recuperável da conexão pelo Windows. |

Dependências declaradas:

```text
mysql-connector-python>=9.0,<28
Pillow>=11,<13
```

Essas faixas não garantem que toda instalação futura use exatamente as mesmas versões.

### Organização dos arquivos

| Arquivo | Conteúdo |
|---|---|
| `app.py` | Programa principal, esquema do banco, migrações, telas, editor, galeria e eventos. |
| `biblioteca.py` | Destaques, cálculo dos troféus, tratamento visual das capas e mosaicos. |
| `calendario.py` | Modelo das datas e calendário interativo. |
| `capas.py` | Pesquisa na Wikipedia, download e conversão de imagens. |
| `contas.py` | Cadastro, autenticação, hashes e atualização de perfil. |
| `conexao_segura.py` | Proteção e recuperação da conexão MySQL. |
| `Abrir biblioteca.bat` | Inicialização no Windows. |
| `requirements.txt` | Dependências externas. |
| `LEIA-ME.txt` | Instruções resumidas de uso. |

### Fluxo de funcionamento

```text
Atalho → arquivo BAT → Python → app.py
    → recuperar conexão protegida ou configurar conexão
    → conectar ao MySQL e verificar tabelas/colunas
    → mostrar perfis
    → validar senha do perfil escolhido
    → carregar sua biblioteca
        → galeria e coleções
        → detalhes do jogo / calendário / troféus
        → configurações de conta
```

É um aplicativo de desktop. Não utiliza React, HTML, CSS, servidor web ou a API HTML5 de arrastar e soltar. O comportamento equivalente foi criado com eventos nativos do Tkinter.

## 4. Conexão e perfis

### Inicialização

A conexão está definida no código como `127.0.0.1:3306`, com tempo limite inicial de cinco segundos e caracteres `utf8mb4`.

`App.startup()` tenta recuperar a configuração protegida. Quando consegue, conecta antes de mostrar os perfis. Se não existir configuração ou houver falha, oferece **Configurar conexão** e **Tentar novamente**.

Na configuração, o aplicativo testa usuário e senha MySQL e tenta salvá-los protegidos. Se o Windows impedir essa gravação, pode continuar conectado na sessão atual, mas será necessário configurar novamente em outra abertura.

### Duas senhas diferentes

- **Senha MySQL:** abre o banco. A configuração inicial usou root.
- **Senha do perfil:** dá acesso à biblioteca pessoal dentro do NEXUS.

Um perfil do NEXUS não cria uma conta MySQL independente.

### Seleção de perfil

A tabela `usuarios` fornece nome e avatar dos cartões. Sem foto, a tela desenha um rosto simples sobre fundo colorido. Há até cinco cartões por linha, em área rolável.

Clicar no perfil existente solicita somente sua senha. Criar perfil solicita nome, senha e confirmação. O nome tem de 1 a 60 caracteres, é único no banco e a senha exige no mínimo oito caracteres.

**Trocar usuário** limpa a biblioteca exibida e retorna aos cartões.

### Preservação dos jogos antigos

A primeira conta criada recebe os jogos ainda sem `usuario_id`. A criação utiliza bloqueio nomeado do MySQL (`GET_LOCK`) e transação para coordenar cadastros simultâneos. As contas seguintes não recebem esses jogos.

## 5. Galeria e destaques

### Visualização principal

Os cartões individuais exibem apenas capas. Nome, plataforma, status e barras ficam no editor aberto pelo clique. Sem capa, aparece um desenho de controle.

A grade calcula aproximadamente uma coluna por 170 pixels, com mínimo de três. A janela principal começa em 1280 × 820, com mínimo de 1050 × 650. É adaptação para desktop, não layout móvel.

Redimensionar agenda a renderização após aproximadamente 120 milissegundos para evitar redesenhos em cada evento intermediário.

### Carregamento das informações

A galeria busca ID, nome, plataforma, percentual, capa, status, favorito, coleção e ordem, necessários à exibição e aos filtros. Ao clicar na capa, o editor consulta novamente todos os detalhes pelo ID do jogo **e do perfil**.

Portanto, o texto fica oculto nos cartões, mas alguns metadados existem em memória para busca e ordenação. Notas, cronograma e troféus são carregados no acesso aos detalhes.

### Busca e filtros

- Busca atual pelo nome do jogo, ignorando maiúsculas/minúsculas.
- Filtro de plataforma.
- Biblioteca, Favoritos, Em andamento, Concluídos e Para jogar no menu.
- Os filtros continuam aplicados dentro de uma coleção.
- Ordenação geral por ordem numérica, nome e identificador.

O status avançado prevalece quando preenchido. Sem ele, 0% gera Na fila; 1–99%, Jogando; e 100%, Concluído.

### Algoritmo de destaque

`highlights()` considera somente `0 < progresso < 100`, excluindo os status explícitos Concluído, Abandonado, Pausado e Na fila. Ordena por percentual decrescente, depois nome e ID.

A tela mostra até quatro resultados, reduzindo a quantidade se faltar largura. Aplica os filtros atuais e oculta essa seção quando uma coleção está aberta.

Exemplo: 0%, 10%, 40%, 80% e 100% resultam em **80%, 40%, 10%**, se não houver status incompatível. O percentual escolhe a ordem, mas não é impresso sobre a capa.

## 6. Coleções

### Estrutura

Cada coleção tem ID, nome e perfil proprietário. Cada jogo pode pertencer a **uma coleção por vez** ou ficar sem coleção. Não há participação simultânea em várias coleções.

O mosaico é uma composição 2 × 2 das primeiras quatro capas, seguindo a ordem dos jogos carregados. Os espaços restantes ficam vazios quando há menos jogos.

Os cartões das coleções mostram nome e quantidade. A regra de apenas imagens aplica-se aos cartões individuais de jogos.

### Operações

- Criar pelo botão **Criar coleção**.
- Abrir clicando no cartão.
- Arrastar uma capa para alterar seu vínculo.
- Renomear ou excluir pelo botão direito.
- Remover o vínculo pelo editor do jogo.
- Definir a sequência em **Ordem na coleção**.

Nomes têm de 1 a 150 caracteres e são únicos dentro do perfil.

### Arrastar e soltar

`cover_tile()` usa eventos de pressionar, mover com o botão pressionado e soltar. Guarda a posição inicial, identifica movimento acima de uma pequena distância, muda o cursor e destaca a coleção de destino em verde.

Soltar sobre uma coleção vincula o jogo; um clique sem arraste abre o editor. Soltar fora de uma coleção não altera o vínculo. Existe rolagem para cima perto do topo.

A consulta de gravação verifica o dono do jogo e da coleção de destino. O fluxo normal não permite atribuir um jogo à coleção de outro perfil.

### Migração dos grupos anteriores

`refresh()` localiza jogos com grupo textual e sem coleção, cria as coleções necessárias, associa os jogos e limpa o campo legado `grupo` após o vínculo. O número `ordem` é mantido.

O campo `grupo` continua na tabela por compatibilidade, mas deixou de ser o mecanismo normal da interface.

### Exclusão

Excluir uma coleção solicita confirmação, remove os vínculos de seus jogos e apaga a coleção em uma transação. Em falha, solicita rollback. **Os jogos são mantidos na biblioteca.**

## 7. Editor, favoritos e troféus

O editor é uma janela modal Tkinter com cabeçalho claro desenhado dentro da janela, ícone de pena, fechamento, duas colunas, rolagem e ações no rodapé.

A esquerda contém informações e troféus. A direita, calendário, datas e capa. Os exemplos Alan Wake 2 e PS5 das referências não foram impostos aos registros: o editor lê o jogo escolhido.

### Campos

| Campo | Regra |
|---|---|
| Nome | Obrigatório, 1–150 caracteres. |
| Plataforma | PC, PS4, PS5, Xbox, Switch ou Outro. |
| Coleção | Exibida como informação; vínculo pelo sistema de coleções. |
| Ordem | Inteiro de 1 a 9999. |
| Progresso | Manual, 0–100. |
| Status | Opcional: Jogando, Na fila, Pausado, Concluído ou Abandonado. |
| Notas | Texto livre, limitado a 60.000 bytes UTF-8 pela interface. |
| Datas | Opcionais, DD/MM/AAAA; término não pode preceder início. |
| Capa | Escolhida localmente ou na pesquisa. |
| Troféus | Obtidos e total, inteiros não negativos. |

Status, percentual jogado e percentual dos troféus são independentes. Alterar um não ajusta automaticamente os outros.

### Salvar e cancelar

Campos, notas, calendário e troféus são confirmados pelo botão Salvar alterações. Cancelar descarta suas mudanças.

**Favoritar e Remover da coleção são ações imediatas**, sem aguardar esse botão. A exclusão também é imediata após confirmação. Não existe desfazer geral.

### Favoritos

Um campo booleano alterna entre verdadeiro/falso, com atualização restrita ao perfil. No layout minimalista, o controle está no editor; o filtro está no menu lateral.

### Troféus

```text
Faltantes = Total − Obtidos
Percentual = (Obtidos / Total) × 100
0 ≤ Obtidos ≤ Total ≤ 1.000.000
```

Total zero resulta em 0% e mensagem para informar o total. A barra acompanha a edição. Valores inválidos exibem aviso e impedem salvar. Apenas obtidos e total são persistidos; faltantes e percentual são calculados.

Não há sincronização de conquistas com Steam, PSN ou Xbox nem cadastro individual de cada troféu.

## 8. Calendário

`Schedule` mantém datas com tipo `single` (avulso) ou `range` (sequência), gravadas em JSON:

```json
{"2026-09-07":"single","2026-09-10":"range","2026-09-11":"range"}
```

| Ação | Resultado |
|---|---|
| Clicar no dia | Marca ou remove dia avulso. |
| Arrastar entre dias | Adiciona sequência, inclusive no sentido inverso. |
| Clicar em Seg, Ter etc. | Marca ocorrências do dia da semana no mês; se todas já estiverem marcadas, remove. |
| Clicar em Sáb e Dom | Seleciona fins de semana do mês exibido. |
| Setas | Navegam entre meses. |
| Limpar seleção | Remove todas as datas selecionadas. |

A seleção semanal grava datas concretas, não uma regra infinita. O arraste opera no mês exibido; intervalos entre meses podem ser digitados. O modelo limita uma sequência contínua a 3.660 dias.

### Aparência

- Pontas de sequência: verde-lima preenchido.
- Intermediários: verde suave e contorno.
- Avulso: círculo verde.
- Futuro: borda tracejada, com prioridade sobre os estilos anteriores.

Futuro é calculado pela data do computador, não como tipo separado no JSON. A semana começa segunda-feira; os meses estão em português e o cálculo considera anos bissextos.

### Datas sincronizadas

A menor data selecionada vira Início; a maior vira Término. Para uma data única, Término fica vazio.

**Editar os campos substitui a seleção pelo intervalo digitado.** Datas esparsas podem virar uma sequência contínua. Datas futuras representam planejamento, não confirmação de jogo concluído.

A passagem do tempo muda a aparência, mas não comprova que a pessoa jogou. Não há duração de sessões. Para registros antigos sem cronograma, as datas existentes são apresentadas como pontos, sem inventar sessões intermediárias.

## 9. Capas e imagens

### Arquivo local

Aceita JPG, JPEG, PNG, WebP e BMP. O Pillow corrige orientação EXIF, converte para RGB, reduz para caber em 900 × 1200 pixels e gera JPEG com qualidade 88. Os bytes ficam no MySQL; o arquivo original pode ser movido depois de salvar.

### Pesquisa online

`buscar_capas()` consulta a Wikipedia em inglês, usando o nome acrescido de `video game`, solicitando até cinco páginas e miniaturas. Resultados sem imagem são descartados.

A busca pode começar ao sair do campo nome, quando ainda não há capa, ou pelo botão. A pessoa seleciona um resultado e confirma a prévia. A persistência ocorre ao salvar o jogo.

A Wikipedia pode retornar logotipo ou outra ilustração, não necessariamente a capa oficial correta.

### Implementação

- URL inicial limitada a HTTPS e aos domínios definidos no módulo.
- Tempo limite de 12 segundos por requisição.
- Limite de 6.000.000 bytes por resposta.
- Busca/download em threads; resultados recebidos por filas.
- Verificação periódica pela interface.
- Verificação de janela ainda existente e descarte de prévias antigas.
- Sem exigência de chave de API.

Capas já salvas podem ser exibidas sem internet, com o MySQL local ativo. `artwork()` adapta a exibição e recorta avatares em círculo; `mosaic()` compõe as coleções.

## 10. Conta e segurança

### Foto e senha

Clicar no nome do perfil na lateral abre Configurações de Conta. O upload mostra prévia circular. Para mudar só a foto, os campos de senha ficam vazios.

Para alterar a senha, são exigidos senha atual, nova senha e confirmação. `update_profile()` valida a senha anterior antes de substituir o hash. A foto aparece na próxima visualização dos cartões de perfil.

### Hash das senhas

`encode_password()` usa PBKDF2-HMAC-SHA256, 600.000 iterações e salt aleatório de 16 bytes, representado em hexadecimal. O formato guardado é `salt:hash`.

`check_password()` refaz a derivação e compara com `hmac.compare_digest`. Não é necessário guardar o texto original da senha para validá-la. Duas pessoas com a mesma senha podem ter hashes diferentes por causa do salt.

### Proteção da conexão MySQL

A senha MySQL precisa ser recuperável para conectar; por isso, não usa o hash dos perfis. `conexao_segura.py` chama `CryptProtectData` e `CryptUnprotectData` do Windows por ctypes.

O arquivo protegido contém usuário e senha. A gravação usa arquivo temporário antes de substituir o destino. O mecanismo está ligado ao contexto Windows do usuário; não é um formato de transferência entre computadores.

Se a proteção falhar, não há fallback silencioso para texto simples: o aplicativo informa que a conexão vale somente para a sessão.

### Separação dos perfis

As consultas de jogos, favoritos, coleções e detalhes usam `usuario_id`. A atribuição à coleção verifica também o dono do destino. A atualização de conta usa o ID autenticado.

É separação dentro do aplicativo. A conexão MySQL é compartilhada, originalmente configurada como root. Não foram criados usuários MySQL com permissões individuais por perfil. O administrador direto do banco continua tendo acesso aos dados.

Não foram implementados recuperação de senha, autenticação de dois fatores, bloqueio por tentativas ou serviço remoto de autenticação.

## 11. Banco de dados

**Banco:** `biblioteca_gamer`. **Codificação solicitada:** `utf8mb4`.

### Tabela usuarios

| Campo | Tipo | Uso |
|---|---|---|
| id | INT, chave primária, autoincremento | Identificador. |
| nome | VARCHAR(60), único, obrigatório | Nome do perfil. |
| senha_hash | VARCHAR(180), obrigatório | Salt e hash. |
| avatar | MEDIUMBLOB, opcional | Imagem. |

### Tabela colecoes

| Campo | Tipo | Uso |
|---|---|---|
| id | INT, chave primária, autoincremento | Identificador. |
| usuario_id | INT, obrigatório | Dono. |
| nome | VARCHAR(150), obrigatório | Nome da coleção. |

Restrição única: combinação de dono e nome.

### Tabela jogos

| Campo | Tipo / padrão | Uso |
|---|---|---|
| id | INT, chave primária, autoincremento | Identificador. |
| nome | VARCHAR(150), obrigatório | Título. |
| plataforma | VARCHAR(30), obrigatório | Plataforma. |
| progresso | INT, padrão 0 | Percentual; CHECK de 0 a 100 no esquema. |
| capa | MEDIUMBLOB | Bytes da imagem. |
| atualizado | TIMESTAMP automático | Última atualização da linha. |
| data_inicio | DATE, opcional | Início. |
| data_termino | DATE, opcional | Término. |
| grupo | VARCHAR(150), padrão vazio | Campo legado para migração. |
| ordem | INT, padrão 1 | Sequência na coleção. |
| usuario_id | INT, opcional no esquema | Dono; vazio permitido para registros antigos. |
| favorito | BOOLEAN, padrão falso | Favorito. |
| colecao_id | INT, opcional | Coleção atual. |
| trofeus_obtidos | INT, padrão 0 | Quantidade obtida. |
| trofeus_total | INT, padrão 0 | Total informado. |
| status_avancado | VARCHAR(40), padrão vazio | Status manual. |
| notas | TEXT, opcional | Anotações. |
| cronograma | JSON, opcional | Datas selecionadas e tipos. |

Existe índice em `usuario_id`. As relações são lógicas: **não foram declaradas chaves estrangeiras** para os vínculos com perfil e coleção. Parte da integridade é garantida pelo código.

O timestamp não é histórico completo de alterações e não mede horas jogadas. O esquema acima foi lido no código; não foi consultado novamente no MySQL instalado do usuário.

## 12. Gravação e migrações

### Exemplo: salvar troféus

1. A pessoa clica na capa.
2. O aplicativo consulta os detalhes pelo ID do jogo e perfil.
3. Os campos recebem os valores atuais.
4. A pessoa altera obtidos e total; a barra é recalculada em memória.
5. Ao salvar, valida nome, datas, ordem, troféus e tamanho das notas.
6. Monta os parâmetros SQL.
7. Executa UPDATE restrito ao jogo e perfil.
8. Confirma, fecha o editor e atualiza a galeria.

Valores fornecidos pelo usuário são enviados como parâmetros `%s` ao conector, não concatenados ao SQL. Nomes de colunas de migração são constantes definidas pelo programa.

`Database.execute()` cria cursor, executa a consulta, confirma com commit e fecha o cursor. Em exceção, solicita rollback. Cadastro do primeiro perfil e exclusão de coleção administram suas transações diretamente.

### Migrações automáticas

`Database.__init__()` cria tabelas ausentes com `CREATE TABLE IF NOT EXISTS`, consulta colunas e acrescenta as novas com `ALTER TABLE`. A conversão de grupos ocorre no carregamento da biblioteca.

Não há ferramenta formal de versionamento de migrações ou reversão automática. A conexão precisa de permissões para criar e alterar essas estruturas. Isso preserva os registros pelo fluxo implementado, mas continua exigindo validação da atualização no MySQL real.

## 13. Testes e evidências

### Confirmado no histórico pelo usuário

- Python 3.13.15 respondeu pelo caminho completo.
- A instalação do conector apareceu concluída no terminal.
- O teste inicial de conexão Python–MySQL foi informado como sucesso.

Isso não equivale a validar todos os recursos adicionados depois.

### Verificações executadas durante o desenvolvimento

| Área | Escopo verificado |
|---|---|
| Sintaxe | Arquivos analisados com `ast.parse`. |
| Imagens | Conversão JPEG, redimensionamento e dimensões do mosaico. |
| Datas | Vazio, data válida, ano bissexto, data inválida e ordem cronológica. |
| Grupos anteriores | Agrupamento, ordenação e validação. |
| Busca de capas | Respostas simuladas, ordenação, resultado vazio, conversão e URL inválida. |
| Contas | Cadastro, nome repetido, senha errada, salt diferente e atribuição dos jogos antigos. |
| Calendário | Marcar/remover, intervalo inverso, estilos, fim de semana, ano bissexto e persistência JSON. |
| Editor | Função de salvar com dependências simuladas; quantidade de parâmetros SQL e perfil. |
| Favoritos | Alternância e consulta restrita ao dono. |
| Destaques | Ordem decrescente e exclusão de status incompatível. |
| Troféus | Cálculo, total zero, limites e valores inválidos. |
| Avatar e senha | Atualização, rejeição da senha atual errada e validação da nova. |
| Coleções | Vínculo, remoção e recusa de destino de outro perfil em banco de teste. |

### O que significa banco de teste

Foram usados objetos simulados e SQLite em memória com adaptação de consultas. Isso verifica regras e parâmetros, mas não comprova todas as operações específicas do MySQL, como DDL, bloqueio nomeado, migrações e comportamento do JSON no servidor real.

### Verificações não concluídas

- Inicialização gráfica no ambiente de testes: erro `Can't find a usable init.tcl`.
- DPAPI: teste sintético retornou erro Windows código 2; a criptografia real não foi confirmada naquele ambiente.
- Acabamento visual final e arraste no Windows do usuário.
- Execução integrada de todas as migrações no banco real.
- Busca online ponta a ponta na versão final.
- Backup e restauração reais.

Esses pontos não demonstram que o recurso falha no computador do usuário. Demonstram que a validação disponível não permite afirmar que passou.

Os scripts ficaram em `work`, com nomes como `test_calendar.py`, `test_profiles.py`, `test_redesign.py` e `test_editor_save_v2.py`. Alguns correspondem a versões anteriores; não constituem uma suíte contínua e completa. Não foram todos reexecutados para escrever este documento.

## 14. Limitações

1. Sem progresso, conquistas ou horas automáticas de serviços externos.
2. Sem versão web, aplicativo móvel ou executável independente do Python.
3. Caminho do Python no iniciador específico da versão 3.13.
4. Endereço e porta MySQL fixos no código.
5. Perfis sem isolamento de contas no próprio servidor MySQL.
6. Uma coleção por jogo; sem tags múltiplas ou coleções inteligentes.
7. Recorrência do calendário limitada ao mês selecionado.
8. Wikipedia pode não oferecer capa correta.
9. As capas do perfil são carregadas e os widgets recriados em renderizações. Bibliotecas grandes podem precisar de cache e paginação.
10. Interface e operações de banco ainda concentradas em `app.py`.
11. Operações MySQL e derivação de senha rodam na execução principal e podem causar pausas. A busca de capas usa threads.
12. Sem lixeira, desfazer geral ou auditoria completa.
13. Sem backup automático e sem exportação/importação dentro do app.
14. Layout não validado em todas as escalas de DPI do Windows.
15. Sem recuperação automática de senha ou bloqueio de tentativas.

Essas melhorias não foram implementadas apenas por serem mencionadas aqui.

## 15. Operação e backup

### Uso cotidiano

Abra pelo atalho, configure a conexão se necessário, escolha o perfil e informe sua senha. Crie jogos e coleções, abra uma capa para editar e use o nome do perfil na lateral para alterar foto ou senha.

### Atualização

Feche o aplicativo antes de substituir arquivos. Mantenha juntos iniciador, módulos e dependências declaradas. O ZIP contém o programa, não os dados pessoais do banco.

Se mover a pasta, atualize o destino do atalho. Alterar a pasta da conversa não faz isso automaticamente.

### Partes do backup

| Parte | O que contém |
|---|---|
| Banco `biblioteca_gamer` | Jogos, capas, perfis, hashes, avatares, coleções, favoritos, datas, cronogramas e troféus. |
| Pasta do aplicativo | Código, iniciador, instruções e dependências declaradas. |
| Configuração de conexão | Arquivo protegido ligado ao Windows; em outro computador, prefira configurar novamente. |

Faça uma exportação lógica completa do banco com ferramenta própria do MySQL e valide a restauração em ambiente separado. Copiar a pasta do aplicativo não copia o banco. Uma cópia dos arquivos internos de um servidor em execução não substitui uma exportação lógica validada.

Nenhuma exportação, restauração ou transferência de dados foi executada nesta documentação.

### Diagnóstico inicial

| Sintoma | Conferir |
|---|---|
| Python não encontrado | Caminho usado pelo `.bat`. |
| Erro de importação | Dependências instaladas no mesmo Python do iniciador. |
| Conexão recusada | Serviço MySQL84 e porta 3306. |
| Conexão não é lembrada | Aviso ao salvar configuração protegida. |
| Perfil não aparece | Se a configuração aponta para a instalação com os dados existentes. |
| Biblioteca vazia | Perfil, busca, plataforma, filtro e coleção aberta. |
| Capa não encontrada | Nome completo do jogo ou arquivo local. |
| Troféus não salvam | Inteiros e obtidos menor ou igual ao total. |
| Atualização sem efeito | Destino do atalho e instâncias antigas ainda abertas. |

## 16. Manutenção do código

| Necessidade | Ponto inicial |
|---|---|
| Alterar esquema | `Database.__init__()` em `app.py`. |
| Entrada e conexão | `startup()` e `configure_connection()`. |
| Perfis | `account_screen()` e `profile_login()`. |
| Galeria | `render()`, `resize_gallery()` e `cover_tile()`. |
| Destaques | `highlights()` em `biblioteca.py`. |
| Coleções | `refresh()`, `assign_collection()` e `collection_menu()`. |
| Campos do jogo | `editor()`, validação e INSERT/UPDATE. |
| Troféus | `trophy_values()` e widgets do editor. |
| Calendário | `Schedule` e `GameCalendar`. |
| Fonte de capas | `capas.py` e o fluxo de prévia na interface. |
| Autenticação | `contas.py`. |
| Proteção MySQL | `conexao_segura.py`. |

Ao criar um campo persistente, revisar coluna, carregamento, validação e gravação. Ao adicionar recurso individual, manter `usuario_id` nas consultas de leitura e escrita.

Alterações visuais exigem teste com a janela aberta. Alterações de esquema exigem teste de migração no MySQL com dados representativos. Testes simulados continuam úteis, mas não substituem essas verificações.

## 17. Glossário

- **Perfil:** identidade dentro do NEXUS com biblioteca própria.
- **Coleção:** pasta lógica de jogos de um perfil.
- **Modal:** janela de uma ação que bloqueia temporariamente a interação com a anterior.
- **Persistência:** informação gravada que sobrevive ao fechamento do programa.
- **BLOB:** campo de bytes, usado para imagens.
- **JSON:** formato estruturado usado no cronograma.
- **Hash de senha:** valor derivado usado para validação sem armazenar o texto original.
- **Salt:** valor aleatório individual usado na derivação do hash.
- **DPAPI:** proteção do Windows para dados recuperáveis, como a conexão MySQL.
- **Transação:** operações confirmadas por commit ou desfeitas por rollback.
- **Migração:** adaptação do esquema e dados de uma versão anterior.
- **Mock:** substituição controlada de uma dependência para teste.

---

**Registro de escopo:** documentação produzida pela inspeção dos arquivos. Não foram lidas senhas, consultados registros pessoais do banco, alterados jogos ou modificadas configurações do Windows para escrevê-la.

