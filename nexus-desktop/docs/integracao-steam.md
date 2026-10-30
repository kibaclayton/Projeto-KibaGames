# Integração opcional com a Steam: estudo (25/10/2026)

Pergunta da entrega 9: dá para vincular a conta Steam, descobrir os jogos que a pessoa de fato iniciou e sincronizar conquistas, só por mecanismos oficiais e permitidos?

## O que a Web API oficial permite (documentação Valve)

| Necessidade | Endpoint oficial | Exige | Observações |
|---|---|---|---|
| Jogos possuídos, com minutos jogados (`playtime_forever`, `playtime_2weeks`) | `IPlayerService/GetOwnedGames` (v1) | chave Web API + SteamID64 | Só responde se a privacidade "Detalhes do jogo" do perfil for pública ou a chave for da própria conta. Não prova que o jogo foi aberto agora. |
| Jogos jogados nas últimas duas semanas | `IPlayerService/GetRecentlyPlayedGames` (v1) | chave + SteamID64 | Mesma regra de privacidade. É a melhor aproximação oficial de "jogos que eu realmente iniciei". |
| Jogo aberto neste momento | `ISteamUser/GetPlayerSummaries` (v2), campo `gameid` | chave + SteamID64 | Só com perfil público e usuário online. Mostra o jogo atual, não um histórico. |
| Conquistas obtidas | `ISteamUserStats/GetPlayerAchievements` (v1) | chave + SteamID64 + appid | Perfil com "Detalhes do jogo" públicos; devolve cada conquista com `achieved` e data. |
| Total de conquistas da edição | `ISteamUserStats/GetSchemaForGame` (v2) | chave + appid | Independe do perfil. (Sem chave, a loja pública já informa `achievements.total`, que o Nexus usa hoje.) |

Fontes: <https://partner.steamgames.com/doc/webapi/IPlayerService>, <https://partner.steamgames.com/doc/webapi/ISteamUserStats>, <https://partner.steamgames.com/doc/webapi_overview>.

## Requisitos práticos

- **Chave Web API pessoal**: obtida em <https://steamcommunity.com/dev/apikey>, com a conta da própria pessoa (exige conta com compra e um "domínio", que pode ser qualquer nome). A chave identifica a conta e dá acesso aos seus dados; precisa ficar só num arquivo local protegido, fora do navegador, dos logs e do Git.
- **SteamID64**: aparece na URL do perfil ou em "Dados da conta". Sem ele nada funciona.
- **Privacidade do perfil**: "Detalhes do jogo" precisa estar público para possuídos, recentes e conquistas.
- Limite oficial: 100.000 chamadas por dia por chave; o Nexus usaria dezenas.

## Conclusão

- **Viável com consentimento e chave**: importar jogos "recentemente jogados" (ou possuídos com tempo registrado), deduplicar por appid (o Nexus já guarda `fonte_externa='steam'` + `id_externo=appid`), e sincronizar conquistas obtidas/total por appid sob demanda ou a cada abertura, com registro da última sincronização e tratamento de perfil privado/offline.
- **Não viável de forma confiável**: "detectar que o jogo foi iniciado" em tempo real. `GetPlayerSummaries` só mostra o jogo aberto enquanto a pessoa está online e com perfil público; a alternativa de ler processos do Windows foi descartada, como o prompt pediu, por depender de varredura local sem razão técnica comprovada.
- **Não implementado nesta entrega**, porque exige cadastro da chave, o SteamID e a decisão explícita de ligar a conta. O provedor já tem o lugar certo para entrar: `covers.py` (SOURCES/DETAILS), `igdb.py` como modelo de chave local (`igdb.json`), e os campos `fonte_externa`/`id_externo` para deduplicar.

## Implementado em 25/10/2026 (à noite)

O caminho "viável" acima virou código em `backend/nexus_backend/trophies.py` e no painel *Troféus e conquistas* de *Conta e preferências*: vínculo com chave + SteamID64 (só neste computador, arquivo `steam-perfil-{id}.json`, um por perfil), lista de jogos recentes ou possuídos com tempo de jogo, importação com ficha/capa/conquistas e sincronização de obtidos/total por appid. O **RetroAchievements** entrou pelo mesmo painel (chave de API web + usuário, `retroachievements-perfil-{id}.json`), por ter API oficial documentada. A pesquisa do mesmo dia confirmou que PlayStation, Xbox, Nintendo e Epic não têm API oficial de troféus para o usuário final (só bibliotecas não oficiais que usam a sessão da conta, com risco de banimento), por isso ficaram de fora. Detalhes e testes em [ATUALIZACAO-0.3.md](../ATUALIZACAO-0.3.md).

## Como seria ligar (texto original do estudo)

1. Criar `steam.json` na pasta de dados com `{"api_key": "...", "steam_id": "..."}` (o app pode oferecer esta tela depois).
2. Em *Conta e preferências*, "Vincular Steam": lista os jogos recentes com prévia e caixas de seleção; só os marcados entram, sem duplicar appids já existentes e sem tocar progresso, notas, datas ou capas escolhidas.
3. "Sincronizar conquistas agora": para cada jogo com appid, atualiza obtidos e total, guardando a data; conta privada ou offline gera aviso, nunca zera valores.
4. "Desvincular" apaga `steam.json` e para a sincronização.

Testes automatizados usariam respostas simuladas; a validação real precisaria da sua conta, com seu consentimento, e nunca da sua senha.
