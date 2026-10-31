"""Busca de jogos pelo nome e detalhes por identificador em fontes públicas sem chave.

Cada fonte é um provedor com duas operações: `search(nome)` devolve candidatos resumidos com um identificador estável
(appid da Steam, QID do Wikidata) e `details(id)` devolve a ficha completa do mesmo jogo, com a capa montada pelo
próprio serviço a partir desse identificador. A interface nunca escolhe a URL final: ela só devolve `fonte + id`, e o
serviço refaz o caminho até a imagem dentro da lista fechada de hosts. Todas as chamadas usam o `fetch` endurecido de
`images.py` (HTTPS, IP público fixado, redirecionamento revalidado) e passam por um cache curto em memória.

Fontes com chave (IGDB, RAWG, SteamGridDB) entram no mesmo formato de provedor; a chave ficaria num arquivo da pasta
de dados, nunca no front-end nem no Git. A ausência de uma fonte nunca derruba as outras.
"""
from collections import deque, OrderedDict
import html
import http.client
import json
import re
import threading
import time
from urllib.parse import quote, urlencode, urlsplit

from datetime import datetime, timezone

from . import igdb
from .images import IMAGE_TYPES, MAX_BYTES, fetch
from .models import Ficha
from .platforms import nexus_platforms, suggest_genre

MAX_JSON_BYTES = 1024 * 1024
MAX_PREVIEW_BYTES = 3 * 1024 * 1024
MAX_PER_SOURCE = 6
MAX_RESULTS = 12
MAX_DESCRIPTION = 2000
SEARCH_TIMEOUT = 8
SEARCH_CACHE_SECONDS = 10 * 60
DETAILS_CACHE_SECONDS = 60 * 60

STEAM_HOSTS = {'store.steampowered.com'}
# O CDN da Steam redireciona as variantes cloudflare/akamai para shared.steamstatic.com; todas ficam na lista fechada.
STEAM_IMAGE_HOSTS = {'shared.steamstatic.com', 'cdn.steamstatic.com', 'cdn.cloudflare.steamstatic.com', 'cdn.akamai.steamstatic.com',
                     'shared.cloudflare.steamstatic.com', 'shared.akamai.steamstatic.com'}
STEAM_IMAGE_BASE = 'https://shared.steamstatic.com/store_item_assets/steam/apps'
WIKIPEDIA_HOSTS = {'pt.wikipedia.org', 'en.wikipedia.org'}
WIKIDATA_HOSTS = {'www.wikidata.org'}
WIKIPEDIA_IMAGE_HOSTS = {'upload.wikimedia.org'}
RETRO_IMAGE_HOSTS = {'media.retroachievements.org'}  # capas e medalhas dos jogos vinculados pelo RetroAchievements (trophies.py)
STEAM_ICON_HOSTS = {'steamcdn-a.akamaihd.net', 'media.steampowered.com'}  # ícones de conquistas da Steam fora do CDN de capas
IMAGE_HOSTS = {'steam': STEAM_IMAGE_HOSTS, 'wikipedia': WIKIPEDIA_IMAGE_HOSTS, 'igdb': igdb.IMAGE_HOSTS, 'retroachievements': RETRO_IMAGE_HOSTS}
# Famílias de plataforma para o filtro da busca; nomes vindos das fontes são comparados por estas expressões.
FAMILY_PATTERNS = {
    'pc': re.compile(r'windows|\bpc\b|mac|linux|steam', re.I), 'playstation': re.compile(r'playstation|\bps[1-5p]\b|vita', re.I),
    'xbox': re.compile(r'xbox', re.I), 'nintendo': re.compile(r'nintendo|switch|\bwii|game ?boy|\b3?ds\b|gamecube|n64|\bs?nes\b', re.I),
}


def matches_family(platforms: list[str], family: str) -> bool:
    """Um candidato só entra num filtro de família quando alguma plataforma conhecida dele casa; sem plataformas, fica de fora."""
    if family not in FAMILY_PATTERNS:
        return True
    return any(FAMILY_PATTERNS[family].search(name) for name in platforms)
# A loja marca trilhas sonoras, artbooks e upgrades como "app"; estes termos no nome indicam que não é o jogo em si.
NOT_A_GAME = ('soundtrack', 'trilha sonora', 'artbook', 'art book', 'upgrade', 'season pass', 'passe de temporada', 'dlc', 'demo',
              'pacote de', 'bundle', 'expansion pass', 'expansão', 'skin pack', 'wallpaper', 'conteúdo adicional', 'roupa de', 'costume',
              'dedicated server', 'servidor dedicado', 'trailer', 'playtest')
STEAM_PLATFORM_LABELS = {'windows': 'Windows', 'mac': 'macOS', 'linux': 'Linux'}
MONTHS = {'jan': 1, 'fev': 2, 'feb': 2, 'mar': 3, 'abr': 4, 'apr': 4, 'mai': 5, 'may': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'aug': 8,
          'set': 9, 'sep': 9, 'out': 10, 'oct': 10, 'nov': 11, 'dez': 12, 'dec': 12}

# Wikidata: propriedades da ficha de um jogo e rótulos das plataformas mais comuns (evita uma chamada extra na busca).
P_INSTANCE_OF, P_PLATFORM, P_GENRE, P_RELEASE, P_DEVELOPER, P_PUBLISHER, P_STEAM_APP = 'P31', 'P400', 'P136', 'P577', 'P178', 'P123', 'P1733'
Q_VIDEO_GAME = 'Q7889'
PLATFORM_LABELS = {'Q1406': 'Windows', 'Q14116': 'macOS', 'Q388': 'Linux', 'Q63184502': 'PlayStation 5', 'Q5014725': 'PlayStation 4',
                   'Q10683': 'PlayStation 3', 'Q98973368': 'Xbox Series X e Series S', 'Q13361286': 'Xbox One', 'Q48263': 'Xbox 360',
                   'Q19610114': 'Nintendo Switch', 'Q122761124': 'Nintendo Switch 2', 'Q48493': 'iOS', 'Q94': 'Android'}


def fetch_json(url: str, allowed_hosts: set[str]) -> dict:
    content_type, data = fetch(url, 'application/json', ('application/json',), MAX_JSON_BYTES, allowed_hosts, SEARCH_TIMEOUT)
    try:
        result = json.loads(data)
    except ValueError as exc:
        raise ValueError('Resposta inválida da fonte.') from exc
    if not isinstance(result, dict):
        raise ValueError('Resposta inválida da fonte.')
    return result


def _image_allowed(url: str, hosts: set[str]) -> bool:
    parts = urlsplit(url or '')
    return parts.scheme == 'https' and parts.hostname in hosts and not parts.username and parts.port in (None, 443)


def fetch_preview(url: str) -> tuple[str, bytes]:
    """Prévia de um candidato, buscada pelo serviço: a interface nunca fala direto com os CDNs das fontes."""
    hosts = STEAM_IMAGE_HOSTS | STEAM_ICON_HOSTS | WIKIPEDIA_IMAGE_HOSTS | igdb.IMAGE_HOSTS | RETRO_IMAGE_HOSTS
    if not _image_allowed(url, hosts):
        raise ValueError('Prévia fora das fontes permitidas.')
    return fetch(url, 'image/png,image/jpeg,image/webp', IMAGE_TYPES, MAX_PREVIEW_BYTES, hosts, 10)


def download_cover(details: dict) -> bytes:
    """Baixa a capa de uma ficha de detalhes; a URL foi montada pelo serviço e precisa estar nos hosts da própria fonte."""
    url, hosts = details.get('imagem') or '', IMAGE_HOSTS.get(details.get('fonte'), set())
    if not _image_allowed(url, hosts):
        raise ValueError('Esta fonte não oferece uma capa para o jogo.')
    return fetch(url, 'image/png,image/jpeg,image/webp', IMAGE_TYPES, MAX_BYTES, hosts)[1]


def _origin_allowed(url: str) -> bool:
    """Links de origem só para páginas das próprias fontes; qualquer outro valor é descartado antes de chegar ao navegador."""
    parts = urlsplit(url or '')
    return (parts.scheme == 'https' and parts.hostname in (STEAM_HOSTS | WIKIPEDIA_HOSTS | WIKIDATA_HOSTS) and not parts.username
            and parts.port in (None, 443) and not any(c.isspace() or ord(c) < 32 for c in url))


def _text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ''
    # Corta antes do regex e limita cada tag para que texto hostil não custe tempo quadrático de CPU.
    clean = html.unescape(re.sub(r'<[^<>]{0,500}>', ' ', value[:limit * 4]))
    return re.sub(r'\s+([!?,.;:])', r'\1', re.sub(r'\s+', ' ', clean)).strip()[:limit]


def _html_lines(value, limit: int) -> str:
    """HTML curto (requisitos da Steam) → texto com uma linha por item, sem tags nem o rótulo "Mínimos:/Recomendados:"."""
    if not isinstance(value, str):
        return ''
    text = re.sub(r'<br\s*/?>|</li>|</p>|</ul>', '\n', value[:limit * 4], flags=re.I)
    text = html.unescape(re.sub(r'<[^<>]{0,500}>', ' ', text))
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.split('\n')]
    lines = [line for line in lines if line and not re.fullmatch(r'(m[ií]nimos?|recomendados?|minimum|recommended):?', line, re.I)]
    return '\n'.join(lines)[:limit]


def _languages(value) -> list[str]:
    """"Português - Brasil<strong>*</strong>, Inglês<br>*idiomas com áudio" → ['Português - Brasil (áudio)', 'Inglês']."""
    if not isinstance(value, str):
        return []
    head = re.split(r'<br\s*/?>', value[:4000], maxsplit=1, flags=re.I)[0]
    head = html.unescape(re.sub(r'<[^<>]{0,500}>', '', head))
    result = []
    for part in head.split(','):
        name = re.sub(r'\s+', ' ', part).strip()
        audio = name.endswith('*')
        name = name.rstrip('* ').strip()[:50]
        label = name + (' (áudio)' if audio else '')
        if name and label not in result:
            result.append(label)
    return result[:60]


RATING_SYSTEMS = (('dejus', 'ClassInd'), ('pegi', 'PEGI'), ('esrb', 'ESRB'), ('usk', 'USK'))


def _age_rating(ratings) -> tuple[str, str]:
    """Classificação indicativa: ClassInd (Brasil) primeiro, depois PEGI, ESRB e USK, com os descritores da fonte."""
    if not isinstance(ratings, dict):
        return '', ''
    for key, label in RATING_SYSTEMS:
        entry = ratings.get(key)
        rating = _text(entry.get('rating'), 20) if isinstance(entry, dict) else ''
        if not rating:
            continue
        value = ('Livre' if rating.lower() == 'l' else f'{rating} anos') if key == 'dejus' else rating.upper()
        return f'{label} {value}'[:80], _text(entry.get('descriptors'), 300)
    return '', ''


def _strings(values, limit: int = 8) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        text = _text(value, 120)
        if text and text not in result:
            result.append(text)
    return result[:limit]


def parse_steam_date(text: str) -> tuple[str | None, int | None]:
    """Datas da loja ("24 fev. 2017", "24 Feb, 2017", "Feb 24, 2017" ou só "2017") viram (ISO ou None, ano ou None)."""
    text = (text or '').strip()
    year = re.search(r'\b(19\d{2}|20\d{2})\b', text)
    if not year:
        return None, None
    rest = text.replace(year.group(1), ' ')
    day = re.search(r'\b([0-3]?\d)\b', rest)
    month = next((number for key, number in MONTHS.items() if re.search(r'\b' + key, rest, re.I)), None)
    if day and month and 1 <= int(day.group(1)) <= 31:
        return f'{int(year.group(1)):04d}-{month:02d}-{int(day.group(1)):02d}', int(year.group(1))
    return None, int(year.group(1))


def _candidate(source: str, external_id: str, title: str, image: str, preview: str, origin: str, year=None, platforms=()) -> dict:
    return {'fonte': source, 'id': external_id, 'titulo': title, 'imagem': image, 'previa': preview, 'origem': origin,
            'ano': year, 'plataformas': list(platforms)}


def _details(source: str, external_id: str, title: str, image: str | None, origin: str, **extra) -> dict:
    """Ficha tipada e fechada: só estes campos chegam ao navegador, nunca o payload bruto do provedor."""
    platforms = extra.get('plataformas', [])
    genres = extra.get('generos', [])
    return {'fonte': source, 'id': external_id, 'titulo': title, 'imagem': image, 'origem': origin,
            'data_lancamento': extra.get('data_lancamento'), 'ano': extra.get('ano'),
            'plataformas': platforms, 'plataformas_nexus': nexus_platforms(platforms),
            'generos': genres, 'genero': suggest_genre(genres),
            'desenvolvedores': extra.get('desenvolvedores', [])[:8], 'publicadoras': extra.get('publicadoras', [])[:8],
            'descricao': extra.get('descricao', ''), 'atribuicao': SOURCE_ATTRIBUTION[source], 'parcial': bool(extra.get('parcial', False)),
            # Ficha completa (requisitos, idiomas, classificação, tempo de jogo, categorias), já validada nos limites do modelo.
            'ficha': Ficha.model_validate(extra.get('ficha') or {}).model_dump(),
            # Total de troféus/conquistas da edição consultada, quando a fonte o publica; zero ou ausência viram "não informado" (None).
            'trofeus_total': extra.get('trofeus_total'), 'trofeus_fonte': source if extra.get('trofeus_total') else '',
            'trofeus_escopo': 'jogo base' if extra.get('trofeus_total') else '',
            'trofeus_consultado_em': datetime.now(timezone.utc).isoformat(timespec='seconds') if extra.get('trofeus_total') else None}


# --- Steam -----------------------------------------------------------------------------------------------------------

def steam_image(app_id) -> str:
    # A variante "_2x" existe para quase todos os jogos; a sem sufixo falta em muitos, então a prévia usa a mesma imagem.
    return f'{STEAM_IMAGE_BASE}/{app_id}/library_600x900_2x.jpg'


def search_steam(name: str, fetch_json=fetch_json) -> list[dict]:
    """Loja Steam: busca pública em português; arte oficial de biblioteca em 3:4 (600x900). Endpoint sem documentação oficial."""
    url = 'https://store.steampowered.com/api/storesearch/?' + urlencode({'term': name, 'l': 'portuguese', 'cc': 'BR'})
    result = fetch_json(url, STEAM_HOSTS)
    items = []
    for item in result.get('items', []):
        if len(items) >= MAX_PER_SOURCE:
            break
        app_id, title = item.get('id'), _text(item.get('name'), 150)
        if type(app_id) is not int or not 0 < app_id < 10 ** 10 or not title or any(term in title.lower() for term in NOT_A_GAME):
            continue
        flags = item.get('platforms') if isinstance(item.get('platforms'), dict) else {}
        platforms = [label for key, label in STEAM_PLATFORM_LABELS.items() if flags.get(key)]
        image = steam_image(app_id)
        items.append(_candidate('steam', str(app_id), title, image, image, f'https://store.steampowered.com/app/{app_id}/', None, platforms))
    return [item for item in items if _image_allowed(item['imagem'], STEAM_IMAGE_HOSTS) and _image_allowed(item['previa'], STEAM_IMAGE_HOSTS)]


def steam_details(app_id: str, fetch_json=fetch_json) -> dict:
    """Ficha da loja (appdetails) do mesmo appid do candidato: gêneros em português, lançamento, estúdios, plataformas."""
    if not re.fullmatch(r'[0-9]{1,10}', app_id):
        raise ValueError('Identificador inválido para a Steam.')
    url = 'https://store.steampowered.com/api/appdetails?' + urlencode({'appids': app_id, 'l': 'portuguese', 'cc': 'BR',
                                                                        'filters': 'basic,genres,release_date,developers,publishers,platforms,achievements,'
                                                                                   'pc_requirements,supported_languages,ratings,metacritic,categories'})
    entry = fetch_json(url, STEAM_HOSTS).get(app_id)
    data = entry.get('data') if isinstance(entry, dict) and entry.get('success') else None
    if not isinstance(data, dict) or not isinstance(data.get('name'), str):
        raise ValueError('Jogo não encontrado na Steam.')
    release = data.get('release_date') if isinstance(data.get('release_date'), dict) else {}
    date, year = parse_steam_date(release.get('date', '')) if not release.get('coming_soon') else (None, None)
    flags = data.get('platforms') if isinstance(data.get('platforms'), dict) else {}
    genres = [genre.get('description') for genre in data.get('genres', []) if isinstance(genre, dict)] if isinstance(data.get('genres'), list) else []
    achievements = data.get('achievements') if isinstance(data.get('achievements'), dict) else {}
    total = achievements.get('total')
    trophies = total if type(total) is int and 0 < total <= 100000 else None  # Steam só conta conquistas do jogo base; zero = não informado.
    requirements = data.get('pc_requirements') if isinstance(data.get('pc_requirements'), dict) else {}
    rating, rating_detail = _age_rating(data.get('ratings'))
    metacritic = data.get('metacritic', {}).get('score') if isinstance(data.get('metacritic'), dict) else None
    categories = [c.get('description') for c in data.get('categories', []) if isinstance(c, dict)] if isinstance(data.get('categories'), list) else []
    ficha = {'requisitos_minimos': _html_lines(requirements.get('minimum'), 3000), 'requisitos_recomendados': _html_lines(requirements.get('recommended'), 3000),
             'idiomas': _languages(data.get('supported_languages')), 'classificacao': rating, 'classificacao_detalhe': rating_detail,
             'metacritic': metacritic if type(metacritic) is int and 0 <= metacritic <= 100 else None, 'categorias': _strings(categories, 30)}
    return _details('steam', app_id, _text(data['name'], 150), steam_image(app_id), f'https://store.steampowered.com/app/{app_id}/',
                    data_lancamento=date, ano=year, plataformas=[label for key, label in STEAM_PLATFORM_LABELS.items() if flags.get(key)],
                    generos=_strings(genres), desenvolvedores=_strings(data.get('developers')), publicadoras=_strings(data.get('publishers')),
                    descricao=_text(data.get('short_description'), MAX_DESCRIPTION), trofeus_total=trophies, ficha=ficha)


# --- Wikipedia + Wikidata ----------------------------------------------------------------------------------------------

def _wikidata_entities(ids: list[str], props: str, fetch_json, extra: dict | None = None) -> dict:
    if not ids:
        return {}
    params = {'action': 'wbgetentities', 'format': 'json', 'ids': '|'.join(ids[:50]), 'props': props, 'languages': 'pt-br|pt|en', 'languagefallback': 1, **(extra or {})}
    result = fetch_json('https://www.wikidata.org/w/api.php?' + urlencode(params), WIKIDATA_HOSTS)
    entities = result.get('entities')
    return entities if isinstance(entities, dict) else {}


def _claim_ids(claims: dict, prop: str) -> list[str]:
    ids = []
    for statement in claims.get(prop, []) if isinstance(claims.get(prop), list) else []:
        value = statement.get('mainsnak', {}).get('datavalue', {}).get('value')
        if isinstance(value, dict) and isinstance(value.get('id'), str) and value['id'] not in ids:
            ids.append(value['id'])
    return ids


def _claim_release(claims: dict) -> tuple[str | None, int | None]:
    """Data de lançamento mais antiga: precisão de dia vira ISO; só ano quando a fonte não tem o dia."""
    best: tuple[str | None, int | None] = (None, None)
    for statement in claims.get(P_RELEASE, []) if isinstance(claims.get(P_RELEASE), list) else []:
        value = statement.get('mainsnak', {}).get('datavalue', {}).get('value')
        if not isinstance(value, dict) or not isinstance(value.get('time'), str):
            continue
        match = re.match(r'\+(\d{4})-(\d{2})-(\d{2})', value['time'])
        if not match:
            continue
        year = int(match.group(1))
        full_day = value.get('precision', 0) >= 11 and match.group(2) != '00' and match.group(3) != '00'
        iso = f'{match.group(1)}-{match.group(2)}-{match.group(3)}' if full_day else None
        if best[1] is None or year < best[1] or (year == best[1] and iso and (best[0] is None or iso < best[0])):
            best = (iso, year)
    return best


def _is_game(claims: dict) -> bool:
    return Q_VIDEO_GAME in _claim_ids(claims, P_INSTANCE_OF) or bool(_claim_ids(claims, P_PLATFORM)) or bool(claims.get(P_STEAM_APP))


def _label(entities: dict, qid: str) -> str:
    labels = entities.get(qid, {}).get('labels', {}) if isinstance(entities.get(qid), dict) else {}
    for language in ('pt-br', 'pt', 'en'):
        value = labels.get(language, {}).get('value') if isinstance(labels.get(language), dict) else None
        if isinstance(value, str) and value.strip():
            return _text(value, 120)
    return PLATFORM_LABELS.get(qid, '')


def _wikipedia_pages(language: str, params: dict, fetch_json) -> list[dict]:
    result = fetch_json(f'https://{language}.wikipedia.org/w/api.php?' + urlencode({'action': 'query', 'format': 'json', **params}), WIKIPEDIA_HOSTS)
    pages = result.get('query', {}).get('pages', {})
    return sorted(pages.values(), key=lambda page: page.get('index', 999)) if isinstance(pages, dict) else []


def _page_origin(language: str, page: dict, title: str) -> str:
    url = page.get('fullurl')
    return url if isinstance(url, str) and _origin_allowed(url) else f'https://{language}.wikipedia.org/wiki/{quote(title.replace(" ", "_"))}'


class PartialResult(Exception):
    """Uma fonte respondeu só em parte: carrega os itens obtidos e um aviso; o resultado não entra no cache."""
    def __init__(self, items: list[dict], warning: str):
        super().__init__(warning)
        self.items, self.warning = items, warning


def _page_images(page: dict) -> tuple[str | None, str | None]:
    image = page.get('original', {}).get('source') or page.get('thumbnail', {}).get('source')
    preview = page.get('thumbnail', {}).get('source') or image
    if not image or not _image_allowed(image, WIKIPEDIA_IMAGE_HOSTS) or not _image_allowed(preview, WIKIPEDIA_IMAGE_HOSTS):
        return None, None
    return image, preview


def search_wikipedia(name: str, fetch_json=fetch_json) -> list[dict]:
    """Wikipedia em português e, se faltar, em inglês: imagem principal do artigo (nem sempre a capa oficial).

    O artigo traz o item do Wikidata (`wikibase_item`), que vira o identificador estável do candidato e permite uma
    consulta em lote ao Wikidata para mostrar ano e plataformas e para descartar páginas que não são jogos.
    """
    items: list[dict] = []
    for language, suffix in (('pt', ' jogo eletrônico'), ('en', ' video game')):
        params = {'generator': 'search', 'gsrsearch': name + suffix, 'gsrnamespace': 0, 'gsrlimit': MAX_PER_SOURCE,
                  'prop': 'pageimages|info|pageprops', 'piprop': 'original|thumbnail', 'pithumbsize': 400, 'pilicense': 'any', 'inprop': 'url', 'ppprop': 'wikibase_item'}
        for page in _wikipedia_pages(language, params, fetch_json):
            image, preview = _page_images(page)
            title = _text(page.get('title'), 150)
            page_id = page.get('pageid')
            if not image or not title or type(page_id) is not int or page_id <= 0:
                continue
            qid = page.get('pageprops', {}).get('wikibase_item') if isinstance(page.get('pageprops'), dict) else None
            external_id = qid if isinstance(qid, str) and re.fullmatch(r'Q[0-9]{1,12}', qid) else f'{language}:{page_id}'
            items.append(_candidate('wikipedia', external_id, title, image, preview, _page_origin(language, page, title)))
        if items:
            break
    qids = [item['id'] for item in items if item['id'].startswith('Q')]
    if qids:
        try:
            entities = _wikidata_entities(qids, 'claims', fetch_json)
        except (ValueError, OSError, http.client.HTTPException) as exc:
            # Sem o Wikidata os candidatos continuam, só sem ano, plataformas e filtro; o aviso impede o cache do resultado parcial.
            raise PartialResult(items[:MAX_PER_SOURCE], f'Wikidata indisponível no momento ({exc}); ano e plataformas ficaram de fora.') from exc
        kept = []
        for item in items:
            claims = entities.get(item['id'], {}).get('claims') if isinstance(entities.get(item['id']), dict) else None
            if isinstance(claims, dict):
                if not _is_game(claims):
                    continue  # Premiações, séries e pessoas com a palavra no título não são jogos.
                item['ano'] = _claim_release(claims)[1]
                item['plataformas'] = [PLATFORM_LABELS[qid] for qid in _claim_ids(claims, P_PLATFORM) if qid in PLATFORM_LABELS][:8]
            kept.append(item)
        items = kept
    return items[:MAX_PER_SOURCE]


def wikipedia_details(external_id: str, fetch_json=fetch_json) -> dict:
    """Ficha do mesmo artigo/item do candidato: dados estruturados do Wikidata (CC0) e resumo + imagem da Wikipedia."""
    if re.fullmatch(r'Q[0-9]{1,12}', external_id):
        entity = _wikidata_entities([external_id], 'claims|sitelinks/urls|labels', fetch_json, {'sitefilter': 'ptwiki|enwiki'}).get(external_id)
        if not isinstance(entity, dict) or 'missing' in entity or not isinstance(entity.get('claims'), dict):
            raise ValueError('Jogo não encontrado no Wikidata.')
        claims = entity['claims']
        refs = {prop: _claim_ids(claims, prop)[:8] for prop in (P_PLATFORM, P_GENRE, P_DEVELOPER, P_PUBLISHER)}
        needed = sorted({qid for ids in refs.values() for qid in ids if qid not in PLATFORM_LABELS})
        labels = _wikidata_entities(needed, 'labels', fetch_json) if needed else {}
        names = {prop: [label for label in (_label(labels, qid) for qid in ids) if label] for prop, ids in refs.items()}
        date, year = _claim_release(claims)
        sitelinks = entity.get('sitelinks') if isinstance(entity.get('sitelinks'), dict) else {}
        language = 'pt' if isinstance(sitelinks.get('ptwiki'), dict) else 'en'
        link = sitelinks.get(language + 'wiki') if isinstance(sitelinks.get(language + 'wiki'), dict) else {}
        title, origin = _label({external_id: entity}, external_id) or external_id, f'https://www.wikidata.org/wiki/{external_id}'
        image, summary, partial = None, '', False
        if isinstance(link.get('title'), str):
            title = _text(link['title'], 150)
            origin = _page_origin(language, {'fullurl': link.get('url')}, title)
            try:
                image, summary = _wikipedia_summary(language, {'titles': link['title']}, fetch_json)
            except (ValueError, OSError, http.client.HTTPException):
                partial = True  # A ficha do Wikidata basta; capa e resumo ficam vazios e o resultado não entra no cache.
        return _details('wikipedia', external_id, title, image, origin, data_lancamento=date, ano=year, plataformas=names[P_PLATFORM],
                        generos=names[P_GENRE], desenvolvedores=names[P_DEVELOPER], publicadoras=names[P_PUBLISHER], descricao=summary, parcial=partial)
    match = re.fullmatch(r'(pt|en):([0-9]{1,12})', external_id)
    if not match:
        raise ValueError('Identificador inválido para a Wikipedia.')
    language, page_id = match.groups()
    pages = _wikipedia_pages(language, {'pageids': page_id, 'prop': 'extracts|pageimages|info', 'exintro': 1, 'explaintext': 1, 'exsentences': 3,
                                        'piprop': 'original|thumbnail', 'pithumbsize': 400, 'pilicense': 'any', 'inprop': 'url'}, fetch_json)
    page = pages[0] if pages and isinstance(pages[0].get('title'), str) and 'missing' not in pages[0] else None
    if not page:
        raise ValueError('Artigo não encontrado na Wikipedia.')
    image, _preview = _page_images(page)
    title = _text(page['title'], 150)
    return _details('wikipedia', external_id, title, image, _page_origin(language, page, title), descricao=_text(page.get('extract'), MAX_DESCRIPTION))


def _wikipedia_summary(language: str, selector: dict, fetch_json) -> tuple[str | None, str]:
    pages = _wikipedia_pages(language, {**selector, 'prop': 'extracts|pageimages', 'exintro': 1, 'explaintext': 1, 'exsentences': 3,
                                        'piprop': 'original|thumbnail', 'pithumbsize': 400, 'pilicense': 'any'}, fetch_json)
    if not pages:
        return None, ''
    image, _preview = _page_images(pages[0])
    return image, _text(pages[0].get('extract'), MAX_DESCRIPTION)


# --- Provedores, cache e limites ---------------------------------------------------------------------------------------

SOURCES = {'steam': search_steam, 'wikipedia': search_wikipedia, 'igdb': None}  # IGDB é resolvida em search_covers, porque depende de chave local.
DETAILS = {'steam': steam_details, 'wikipedia': wikipedia_details}
SOURCE_LABELS = {'steam': 'Steam', 'wikipedia': 'Wikipedia', 'igdb': 'IGDB', 'retroachievements': 'RetroAchievements'}
SOURCE_ATTRIBUTION = {'steam': 'Dados e capa da loja Steam (Valve).', 'wikipedia': 'Dados do Wikidata (CC0) e resumo/imagem da Wikipedia (CC BY-SA).',
                      'igdb': 'Dados e capas da IGDB (Twitch), uso não comercial.',
                      'retroachievements': 'Dados e imagens do RetroAchievements (comunidade), com a sua chave pessoal.'}
IGDB_HINT = 'IGDB não configurada: consoles dependem da Wikipedia/Wikidata. Para ativar, crie igdb.json na pasta de dados (veja a documentação).'


class Cache:
    """Cache curto em memória para respostas públicas das fontes; a chave inclui fonte e consulta normalizada, nunca o perfil."""
    def __init__(self, seconds: float, max_items: int = 256):
        self.seconds, self.max_items = seconds, max_items
        self.items: OrderedDict = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            entry = self.items.get(key)
            if not entry:
                return None
            if time.monotonic() - entry[0] > self.seconds:
                del self.items[key]
                return None
            self.items.move_to_end(key)
            return json.loads(entry[1])

    def set(self, key, value):
        with self.lock:
            self.items[key] = (time.monotonic(), json.dumps(value, ensure_ascii=False))
            self.items.move_to_end(key)
            while len(self.items) > self.max_items:
                self.items.popitem(last=False)


class Throttle:
    """Limita buscas por perfil para não sobrecarregar as fontes públicas."""
    def __init__(self, limit: int = 20, window: float = 60):
        self.limit, self.window = limit, window
        self.calls: dict[int, deque] = {}
        self.lock = threading.Lock()

    def allow(self, key: int) -> bool:
        now = time.monotonic()
        with self.lock:
            calls = self.calls.setdefault(key, deque())
            while calls and now - calls[0] > self.window:
                calls.popleft()
            if len(calls) >= self.limit:
                return False
            calls.append(now)
            return True


def search_covers(name: str, sources: tuple[str, ...] = ('steam', 'wikipedia'), fetch_json=fetch_json, cache: Cache | None = None,
                  family: str = 'todas', igdb_config: dict | None = None) -> dict:
    """Consulta as fontes pedidas; uma fonte fora do ar vira aviso, sem derrubar as outras. Resultados completos ficam em cache.

    `family` filtra por PC/PlayStation/Xbox/Nintendo: a Steam só responde para PC, a Wikipedia/Wikidata é filtrada pelas
    plataformas do item e a IGDB (quando configurada) recebe o filtro na própria consulta.
    """
    key = json.dumps(['busca', list(sources), ' '.join(name.casefold().split()), family, bool(igdb_config)])
    if cache is not None and (cached := cache.get(key)) is not None:
        return cached
    items, warnings = [], []
    for source in sources:
        if source == 'igdb':
            if not igdb_config:
                if family in ('playstation', 'xbox', 'nintendo') or sources == ('igdb',):
                    warnings.append(IGDB_HINT)
                continue
            try:
                items.extend(igdb.search(igdb_config, name, family))
            except (ValueError, OSError, http.client.HTTPException) as exc:
                warnings.append(f'IGDB indisponível no momento ({exc}).')
            continue
        search = SOURCES.get(source)
        if not search or (source == 'steam' and family not in ('todas', 'pc')):
            continue
        try:
            found = search(name, fetch_json)
            items.extend(item for item in found if source != 'wikipedia' or matches_family(item.get('plataformas', []), family))
        except PartialResult as partial:
            items.extend(partial.items)
            warnings.append(partial.warning)
        except (ValueError, OSError, http.client.HTTPException) as exc:
            warnings.append(f'{SOURCE_LABELS[source]} indisponível no momento ({exc}).')
    result = {'itens': items[:MAX_RESULTS], 'avisos': warnings}
    if cache is not None and not warnings:
        cache.set(key, result)
    return result


def game_details(source: str, external_id: str, fetch_json=fetch_json, cache: Cache | None = None, igdb_config: dict | None = None) -> dict:
    """Ficha completa pelo identificador do provedor; só os campos tipados de `_details` saem daqui."""
    key = json.dumps(['detalhes', source, external_id])
    if cache is not None and (cached := cache.get(key)) is not None:
        return cached
    if source == 'igdb':
        if not igdb_config:
            raise ValueError('IGDB não configurada neste computador.')
        raw = igdb.details(igdb_config, external_id)
        result = _details('igdb', external_id, raw['titulo'], raw['imagem'], raw['origem'], data_lancamento=raw['data_lancamento'], ano=raw['ano'],
                          plataformas=raw['plataformas'], generos=raw['generos'], desenvolvedores=raw['desenvolvedores'], publicadoras=raw['publicadoras'],
                          descricao=_text(raw['descricao'], MAX_DESCRIPTION), ficha=raw.get('ficha'))
        if cache is not None:
            cache.set(key, result)
        return result
    provider = DETAILS.get(source)
    if not provider:
        raise ValueError('Fonte desconhecida.')
    result = provider(external_id, fetch_json)
    if cache is not None and not result.get('parcial'):
        cache.set(key, result)
    return result
