# Nexus Wolf’s — versão 0.3.0

## Atualização atual: etapa 2 e início da etapa 3

O app agora possui executável Windows com serviço integrado e biblioteca conectada: cards, busca, favoritos, coleções, edição e calendário de sessões de jogo (`src/features/library/GameCalendar.tsx` e `schedule.ts`). Abra `../Abrir Nexus.bat`. O acesso pelo celular na rede local (HTTPS com certificado próprio, desligado por padrão, instalável como PWA) as configurações da conta (foto de perfil com recorte em `src/components/AvatarCropper.tsx`, troca de senha e expiração de sessão) a capa automática pelo nome do jogo e a ficha preenchida ao escolher um resultado (Steam e Wikipedia/Wikidata, em `backend/nexus_backend/covers.py`, `platforms.py`, `src/features/library/CoverSearch.tsx` e `coverModel.ts`) estão descritos em [ATUALIZACAO-0.3.md](ATUALIZACAO-0.3.md). Consulte [ATUALIZACAO-0.3.md](ATUALIZACAO-0.3.md) para entrega, testes, importação e pendências. As seções históricas abaixo descrevem a etapa 1 e não representam o estado atual.

## Atualização: etapa 2 implementada

Backend FastAPI/SQLite, migração MySQL, processamento WebP e login de perfis estão implementados. Veja [instruções completas da etapa 2](backend/README.md) para iniciar, importar os dados e testar. As seções abaixo registram a entrega visual da etapa 1; seus limites de backend foram substituídos pela documentação da etapa 2.

Base desktop React + TypeScript + Vite, Tailwind CSS e Tauri 2. Esta etapa cria a estrutura e o Design System do documento arquitetural. O aplicativo Python/MySQL continua no diretório superior.

## Instalador e atualizador

`scripts/build-desktop.ps1` gera, além da release portátil, `release/NexusWolfs-Setup-<versão>-<build>.exe` (Inno Setup 6, por usuário, sem administrador; biblioteca em `%LOCALAPPDATA%\NexusWolfs`, importada da pasta portátil na primeira abertura) e o pacote de atualização `release/<build>.zip` com `release/atualizacao.json`. O aplicativo instalado verifica esse canal em *Conta e preferências → Versão e atualizações*, prepara a versão nova com hash e autoteste, aplica só com confirmação e permite reverter. Detalhes em [ATUALIZACAO-0.3.md](ATUALIZACAO-0.3.md).

## Executar a interface

Use Node.js 22 LTS ou superior e pnpm 11.19.0 (versão fixada em `package.json`). Dentro de `nexus-desktop`:

```powershell
pnpm install
pnpm dev
```

Abra http://127.0.0.1:1420. Para verificar TypeScript e gerar a distribuição web:

```powershell
pnpm build
pnpm preview
```

Para abrir a janela desktop, instale também os pré-requisitos do Tauri no Windows (Rust MSVC, Microsoft C++ Build Tools e WebView2) e execute `pnpm tauri dev`. O instalador de distribuição ainda está desativado; ícone final, assinatura e empacotamento serão tratados posteriormente. O build release usa o subsistema Windows para não abrir um console.

## Estrutura

- `src/App.tsx`: shell responsivo, navegação local, tela inicial e mostruário interativo.
- `src/components/ui.tsx`: botões, painéis e modal nativo com Escape, foco contido e rolagem interna.
- `src/components/Brand.tsx`: monograma vetorial provisório, não o logo ilustrado final.
- `src/theme/ThemeProvider.tsx`: tema escuro padrão, alternância clara e preferência local.
- `src/styles.css`: tokens semânticos, layout, estados de foco, responsividade e movimento reduzido.
- `tailwind.config.js`: tokens exatos do documento; carregado explicitamente via `@config` no Tailwind 4.
- `src-tauri/`: configuração e entrada Rust mínimas, sem permissões de filesystem ou shell.

## Design System

Fundo `#0A0B10`; sidebar `rgba(21, 23, 34, 0.6)` com blur; neon `#9D00FF` e `#FF007F`; sucesso `#00E676`; texto secundário `#8890A5`. Inter é empacotada localmente, sem Google Fonts ou requisições externas. Ícones SVG usam traço 1,5 px. Acentos primários têm variações mais escuras para legibilidade dos rótulos brancos. Tema claro usa tokens semânticos próprios, sem alterar as cores originais de identidade.

A navegação muda entre Biblioteca, Coleções, Favoritos e Design System. O mostruário permite experimentar campos, filtros, botões e progresso sem gravar jogos. Preferências visuais abrem em um modal; o tema é a única preferência persistida nesta etapa (`localStorage`, chave `nexus-wolfs:theme`). Animações respeitam `prefers-reduced-motion`.

## Limites desta etapa

Não há autenticação, serviço FastAPI, SQLite, migração, processamento WebP, cards finais, busca real ou virtualização ainda. Coleções e favoritos têm estados vazios explicitamente identificados. Nenhum dado MySQL é lido ou alterado. A migração exigirá backup, mapeamento de esquema e validação antes de substituir o aplicativo atual. Nenhuma redução específica de RAM ou disco foi medida nesta etapa.

## Validação desta entrega

- Instalação com lockfile `pnpm-lock.yaml`; somente o script de build do esbuild está liberado em `pnpm-workspace.yaml`.
- `pnpm build`: TypeScript estrito e build Vite passaram. JavaScript gerado: aproximadamente 370 kB (117 kB gzip); CSS: 16,5 kB (4,7 kB gzip). Esses números não medem RAM.
- Preview de produção aberto no navegador: navegação, exemplo de progresso chegando a 100%, modal, fechamento via Escape e tema persistente após recarga verificados.
- Layout compacto (viewport solicitado de 390 px): menu e navegação verificados, sem overflow horizontal no conteúdo.
- Nenhum erro de console observado na sessão do preview.
- O servidor `dev` encontrou `Acesso negado` na resolução de dependências pelo esbuild dentro do ambiente restrito desta sessão. O build usa `--configLoader runner`; o preview de produção funcionou. Se ocorrer a mesma limitação, execute `pnpm build` e `pnpm preview` para conferir a interface.
- Rust/Cargo não disponíveis nesta sessão: a compilação Tauri não foi executada. Ícones locais são monogramas provisórios.

## Referências técnicas

- [Tauri com Vite](https://v2.tauri.app/start/frontend/vite/)
- [Pré-requisitos do Tauri](https://v2.tauri.app/start/prerequisites/)
- [Tailwind com Vite](https://tailwindcss.com/docs/installation/using-vite)
- [Compatibilidade de configuração @config](https://tailwindcss.com/docs/functions-and-directives#config-directive)
