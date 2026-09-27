# Biblioteca funcional e abertura integrada — Implementation Plan

> For agentic workers: execução direta nesta sessão, conforme pedido do usuário para concluir a etapa 2 e começar a 3. Aplicar testes e verificação antes de concluir.

**Goal:** entregar abertura única do backend/interface e uma biblioteca funcional com cards, favoritos, busca e edição.

**Architecture:** manter FastAPI/SQLite e o cliente React da etapa 2. Servir o build React também pelo backend para empacotar ambos em um launcher Windows sem console. Tauri permanece como alvo nativo; a alternativa de Python local invisível é permitida pelo documento original, sem exigir Rust/C++ para esta entrega.

**Tech Stack:** React, TypeScript, Tailwind, Framer Motion, Python, FastAPI, SQLite, Pillow, PyInstaller.

**Spec:** `Mestre_Arquitetura_Nexus_Wolfs_Final.docx`, aprovado nas mensagens anteriores; `backend/README.md` descreve o contrato existente.

## Global Constraints
- Tokens de cor e grid de capas 3:4 do documento original.
- Cards: raio 16 px, elevação de 6 px, zoom 5%, animação 300 ms, movimento reduzido respeitado.
- Apenas perfil autenticado acessa jogos; token em memória; senhas antigas preservadas na importação.
- MySQL não pode ser modificado. Migração real somente se a conexão salva estiver acessível.
- Não sobrescrever a biblioteca existente nem criar dados fictícios na biblioteca pessoal.

## Review Focus
- Resposta atrasada de busca/perfil não pode mostrar jogos do perfil anterior.
- Arquivos fora da viewport liberam URLs de Blob e cancelam downloads.
- 0/0 troféus não gera platina; dados inválidos não salvam parcialmente.
- Executável deve abrir a mesma pasta de dados e falhar claramente se outra aplicação ocupar a porta.
- Falha de migração mantém origem e destino existente intactos.

## Tasks
- [x] Runtime: servir frontend e API juntos, diretório estável, launcher sem console, encerramento do serviço e build Windows. EXE real passou no autoteste; inspeção visual nativa não ficou disponível pela ferramenta de janelas.
- [x] Cards: troféus/formulário testados, GameCard, CoverImage com IntersectionObserver, cancelamento, grade/lista e estados vazios.
- [x] Biblioteca: paginação, debounce 300 ms, filtros, favoritos, destaque e atualização após salvar.
- [x] Edição: modal, progresso, troféus, datas, notas e capa; cronograma preservado; coleções e associação.
- [x] Atualização: lançador integrado, acesso ao legado preservado e importador local disponibilizado.
- [ ] Migração dos dados pessoais: bloqueada pela leitura negada da conexão DPAPI. Executar o importador local com a senha fornecida pelo usuário no próprio computador; não houve alteração do MySQL.
- [x] Verificação: 24 testes backend, 4 testes frontend, build, UI isolada, revisão final e limites documentados.

## Execution record
- Base lida; nenhum Rust/MSVC encontrado. Execução na cópia de trabalho existente, que contém as duas etapas ainda não commitadas; não mover os arquivos em uso pelo preview.
- A autorização do usuário cobre a execução direta desta continuação. A especificação visual e a escolha das etapas já foram fornecidas e aprovadas; não repetir pedidos de aprovação.
- Revisão corrigiu filtro `undefined` que causava HTTP 422 e bloqueou salvamento de formulário vazio após falha ao buscar detalhes. Revisão das correções aprovada.
- Continuação de 27/09: usuário autorizou publicação no GitHub e paridade visual app/web. Build agora verifica todos os arquivos por hash e faz autoteste antes de atualizar o lançador. Atualizador de atalho disponível para execução local; atalho antigo encontrado apontava para a cópia legada.
