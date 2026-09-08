# Projeto-KibaGames — NEXUS PLAY LIBRARY

Biblioteca pessoal de jogos para Windows, desenvolvida em **Python, Tkinter e MySQL**.

## Funcionalidades

- Galeria responsiva de capas e detalhes em modal.
- Coleções com mosaicos, ordenação e arrastar e soltar.
- Progresso manual, favoritos e destaques por percentual.
- Calendário com dias avulsos, intervalos e seleção semanal por mês.
- Notas, status, datas e contagem de troféus.
- Perfis separados, senha e avatar circular.
- Busca de capas na Wikipedia com confirmação da imagem.
- Conexão MySQL armazenada com a proteção de dados do Windows (DPAPI).

## Requisitos

- Windows de 64 bits.
- Python 3.13 com Tkinter.
- MySQL Server local na porta 3306; desenvolvimento realizado com a versão 8.4.
- Dependências de `requirements.txt`.

## Instalação

1. Baixe ou clone este repositório.
2. Instale Python e MySQL; mantenha o serviço MySQL iniciado.
3. Abra **Abrir biblioteca.bat**. Ele usa o caminho padrão de instalação do Python 3.13 para o usuário e instala componentes ausentes.
4. Na primeira abertura, use **Configurar conexão** e informe seu usuário e senha MySQL.
5. Crie ou selecione um perfil.

Se o Python estiver em outro caminho, execute no terminal dentro da pasta:

```powershell
python -m pip install -r requirements.txt
python app.py
```

O aplicativo cria o banco `biblioteca_gamer` e suas tabelas. A conexão precisa de permissões para criar e atualizar o esquema. O endereço `127.0.0.1` e a porta `3306` estão definidos em `app.py`.

## Dados e privacidade

Este repositório contém somente código e documentação: não inclui banco de dados, senhas, perfis, capas pessoais ou configuração de conexão.

Os dados ficam no MySQL local. A configuração protegida é criada em `%LOCALAPPDATA%\NexusPlay\conexao.dat`. Ela não deve ser adicionada ao Git. As senhas dos perfis usam PBKDF2-HMAC-SHA256 com salt individual. A separação de perfis ocorre no aplicativo; o administrador do MySQL mantém acesso ao banco.

## Organização

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Interface, persistência e migrações |
| `biblioteca.py` | Destaques, troféus e mosaicos |
| `calendario.py` | Modelo e interface do calendário |
| `capas.py` | Busca e tratamento de capas |
| `contas.py` | Autenticação e configurações de perfil |
| `conexao_segura.py` | Proteção da conexão no Windows |

## Estado da implementação

Projeto em desenvolvimento. Foram verificados sintaxe e comportamentos isolados, incluindo testes com dependências simuladas e SQLite em memória. A validação completa de interface, migrações no MySQL e DPAPI no ambiente de execução ainda está pendente.

O programa não sincroniza progresso ou troféus com Steam, PSN ou Xbox. A busca na Wikipedia pode retornar uma imagem que não seja a capa oficial. Não há backup automático ou recuperação de senha.

Consulte [DOCUMENTACAO.md](DOCUMENTACAO.md) para o histórico, regras, esquema do banco, testes e limitações, e [LEIA-ME.txt](LEIA-ME.txt) para uso cotidiano.
