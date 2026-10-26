# Fontes de metadados de jogos: comparação (24/10/2026)

Levantamento feito para a etapa 10 (ficha do jogo preenchida ao escolher um resultado). Critérios do prompt: cobertura de PC e consoles, qualidade da capa, localização em português, licença e atribuição, limites, estabilidade, necessidade de chave ou cadastro e documentação oficial.

| Fonte | Cadastro/chave | Cobertura | Capa | Português | Licença/atribuição | Limites conhecidos | Documentação |
|---|---|---|---|---|---|---|---|
| **Steam (loja)** | não | só jogos vendidos na Steam (PC; Mac/Linux marcados) | arte oficial de biblioteca 3:4 (`library_600x900`) pelo mesmo appid | gêneros e, quando a loja tem, descrição em pt-BR | uso da loja pública; sem termos de API | cerca de 200 pedidos por 5 minutos (observado pela comunidade, não oficial) | **não oficial** (`storesearch`, `appdetails`) |
| **Wikipedia + Wikidata** | não | ampla, inclui consoles e jogos antigos; depende da existência do artigo/item | imagem principal do artigo (nem sempre a capa oficial, resolução menor) | artigos em pt e rótulos pt/pt-BR; cai para en | Wikidata CC0; texto da Wikipedia CC BY-SA (atribuição e link exibidos) | política de User-Agent; limites generosos | **oficial** (API MediaWiki/Wikibase) |
| **IGDB (Twitch)** | sim: conta Twitch de desenvolvedor, Client ID + token OAuth | a mais completa (PC e consoles, edições, plataformas por lançamento) | capas oficiais em vários tamanhos, ligadas ao mesmo id | nomes alternativos; textos em inglês | gratuita para uso não comercial, atribuição esperada | 4 pedidos por segundo por cliente, até 8 em aberto; 500 resultados por pedido | oficial |
| **RAWG** | sim: chave gratuita | ampla (PC e consoles) | capas de fundo/arte; qualidade variável | inglês | gratuita com crédito e link para RAWG em cada página; uso comercial com limites de público; quota de 20 mil pedidos/mês citada por terceiros, não confirmada | chave obrigatória em todo pedido | oficial (apidocs), termos no próprio site |
| **SteamGridDB** | sim: chave | artes para jogos de PC e alguns consoles | muitas capas feitas pela comunidade | inglês | termos próprios | — | oficial |

## Decisão aplicada

Steam + Wikipedia/Wikidata, sem chave e sem cadastro, porque:

1. O prompt pede para apresentar a comparação e pedir decisão antes de integrar qualquer serviço com cadastro ou pago. IGDB e RAWG exigem conta.
2. A Steam liga capa e ficha pelo mesmo appid; o Wikidata liga ficha e artigo pelo QID e tem documentação oficial, o que cobre a regra "uma fonte sem documentação oficial não pode ser o único pilar".
3. A interface de provedor (`SOURCES`/`DETAILS` em `covers.py`) permite acrescentar IGDB ou RAWG sem mexer no formulário; a chave ficaria num arquivo da pasta de dados (nunca no bundle React, no banco publicado, no log ou no Git), e a ausência dela não quebraria o editor.

## Limitações a considerar antes de decidir

- A Steam não cobre jogos exclusivos de console; para eles a capa vem da Wikipedia e pode não ser a arte oficial.
- A descrição da Steam vem em inglês quando a loja não tem texto em pt-BR.
- Os endpoints da Steam podem mudar sem aviso.

Se quiser cobertura melhor de consoles e capas oficiais, a recomendação é **IGDB** (gratuita, não comercial, conta Twitch): metadados e capas pelo mesmo id, plataformas por lançamento e boa estabilidade. RAWG é a alternativa com cadastro mais simples, mas exige crédito e link em toda página que usa os dados.

Fontes consultadas: páginas de governança e wrappers públicos da IGDB, termos da RAWG reproduzidos no pacote PyPI `rawg` e em `api.apis.guru`, blog do SteamDB e guias da comunidade sobre `appdetails`, documentação da API MediaWiki/Wikibase.

## Complemento de 25/10/2026: ficha completa e troféus

- **Ficha completa** (requisitos mínimos/recomendados, idiomas, classificação indicativa, Metacritic, categorias): vem de `appdetails` da Steam (`pc_requirements`, `supported_languages`, `ratings` com ClassInd/`dejus` antes de PEGI/ESRB/USK, `metacritic`, `categories`). A Wikipedia/Wikidata não traz esses campos. **Tempo de jogo** (história, com extras, 100%) só pela IGDB (`game_time_to_beats`), quando configurada; HowLongToBeat e PSNProfiles não têm API oficial e não são usadas.
- **Troféus por conta**: Steam Web API (chave pessoal + SteamID64) e RetroAchievements (chave de API web + usuário), ambos oficiais e documentados, em `trophies.py`. PlayStation, Xbox, Nintendo e Epic: sem API oficial para o usuário; só caminhos não oficiais com risco de banimento, por isso ficam manuais. Estudo e decisão em [integracao-steam.md](integracao-steam.md).
