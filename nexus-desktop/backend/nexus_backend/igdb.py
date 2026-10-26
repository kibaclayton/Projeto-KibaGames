"""Provedor opcional IGDB (Twitch) para jogos de PlayStation, Xbox, Nintendo e PC.

Exige um cadastro gratuito de desenvolvedor na Twitch: crie um aplicativo em https://dev.twitch.tv/console/apps e copie o
Client ID e o Client Secret para o arquivo `igdb.json` na pasta de dados do Nexus (o caminho aparece na tela de busca):

    {"client_id": "...", "client_secret": "..."}

As credenciais ficam só nesse arquivo local: nunca vão para o navegador, para o Git nem para logs. Sem o arquivo, o
provedor fica desligado e a busca continua com Steam e Wikipedia/Wikidata. Documentação oficial: https://api-docs.igdb.com.
"""
from datetime import datetime, timezone
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

from .images import fetch

IGDB_HOSTS = {'api.igdb.com'}
TOKEN_HOSTS = {'id.twitch.tv'}
IMAGE_HOSTS = {'images.igdb.com'}
IMAGE_BASE = 'https://images.igdb.com/igdb/image/upload'
MAX_JSON_BYTES = 1024 * 1024
TIMEOUT = 8
MAX_RESULTS = 8
# Famílias de plataforma e os ids da IGDB que elas cobrem (consoles atuais e anteriores mais comuns).
FAMILIES = {
    'pc': (6, 14, 3), 'playstation': (7, 8, 9, 48, 167, 38, 46), 'xbox': (11, 12, 49, 169),
    'nintendo': (130, 508, 41, 5, 21, 4, 19, 18, 37, 20, 22, 24, 33),
}
_token_lock = threading.Lock()
_token: dict = {'value': '', 'expires': 0.0, 'client': ''}


def config_path(data_dir: Path) -> Path:
    return Path(data_dir) / 'igdb.json'


def load_config(data_dir: Path) -> dict | None:
    path = config_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        return None
    client_id, secret = data.get('client_id', ''), data.get('client_secret', '')
    if not isinstance(client_id, str) or not isinstance(secret, str) or not re.fullmatch(r'[A-Za-z0-9]{10,64}', client_id) or not re.fullmatch(r'[A-Za-z0-9]{10,64}', secret):
        return None
    return {'client_id': client_id, 'client_secret': secret}


def configured(data_dir: Path) -> bool:
    return load_config(data_dir) is not None


def _json(url: str, hosts: set[str], method: str = 'GET', body: bytes | None = None, headers: dict | None = None, fetch=fetch) -> object:
    content_type, data = fetch(url, 'application/json', ('application/json',), MAX_JSON_BYTES, hosts, TIMEOUT, method=method, body=body, headers=headers)
    try:
        return json.loads(data)
    except ValueError as exc:
        raise ValueError('Resposta inválida da IGDB.') from exc


def access_token(config: dict, fetch=fetch, now=time.monotonic) -> str:
    """Token de aplicativo (client credentials) da Twitch, guardado em memória até perto de expirar."""
    with _token_lock:
        if _token['value'] and _token['client'] == config['client_id'] and now() < _token['expires'] - 60:
            return _token['value']
        query = urlencode({'client_id': config['client_id'], 'client_secret': config['client_secret'], 'grant_type': 'client_credentials'})
        result = _json('https://id.twitch.tv/oauth2/token?' + query, TOKEN_HOSTS, 'POST', b'', {'Content-Length': '0'}, fetch)
        token = result.get('access_token') if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise ValueError('A Twitch não devolveu um token para a IGDB; confira o Client ID e o Client Secret em igdb.json.')
        _token.update(value=token, client=config['client_id'], expires=now() + float(result.get('expires_in', 3600)))
        return token


def _query(config: dict, endpoint: str, body: str, fetch=fetch) -> list:
    headers = {'Client-ID': config['client_id'], 'Authorization': 'Bearer ' + access_token(config, fetch), 'Content-Type': 'text/plain'}
    result = _json(f'https://api.igdb.com/v4/{endpoint}', IGDB_HOSTS, 'POST', body.encode('utf-8'), headers, fetch)
    return result if isinstance(result, list) else []


def _escape(text: str) -> str:
    return re.sub(r'[^\w .:\'’!?&-]', ' ', text, flags=re.UNICODE).strip()[:80]


def cover_url(image_id: str, size: str = 't_cover_big') -> str:
    return f'{IMAGE_BASE}/{size}/{image_id}.jpg'


def _year(stamp) -> int | None:
    return datetime.fromtimestamp(int(stamp), timezone.utc).year if isinstance(stamp, (int, float)) and stamp > 0 else None


def _date(stamp) -> str | None:
    return datetime.fromtimestamp(int(stamp), timezone.utc).date().isoformat() if isinstance(stamp, (int, float)) and stamp > 0 else None


def search(config: dict, name: str, family: str = 'todas', fetch=fetch) -> list[dict]:
    """Candidatos resumidos: título com edição (version_title), plataformas e ano, filtrados pela família pedida."""
    where = ''
    if family in FAMILIES:
        where = f' where platforms = ({",".join(str(i) for i in FAMILIES[family])});'
    body = f'search "{_escape(name)}"; fields name,version_title,cover.image_id,platforms.name,first_release_date,url;{where} limit {MAX_RESULTS};'
    items = []
    for game in _query(config, 'games', body, fetch):
        if not isinstance(game, dict) or not isinstance(game.get('id'), int) or not isinstance(game.get('name'), str):
            continue
        cover = game.get('cover', {}).get('image_id') if isinstance(game.get('cover'), dict) else None
        if not isinstance(cover, str) or not re.fullmatch(r'[a-z0-9]+', cover):
            continue  # Sem capa não há o que mostrar; a ficha de texto sozinha não ajuda a escolher.
        title = game['name'] + (f' ({game["version_title"]})' if isinstance(game.get('version_title'), str) and game['version_title'] else '')
        platforms = [p['name'] for p in game.get('platforms', []) if isinstance(p, dict) and isinstance(p.get('name'), str)][:8]
        items.append({'fonte': 'igdb', 'id': str(game['id']), 'titulo': title[:150], 'imagem': cover_url(cover), 'previa': cover_url(cover, 't_cover_small'),
                      'origem': game.get('url') if isinstance(game.get('url'), str) and game['url'].startswith('https://www.igdb.com/') else f'https://www.igdb.com/games/{game["id"]}',
                      'ano': _year(game.get('first_release_date')), 'plataformas': platforms})
    return items


def details(config: dict, external_id: str, fetch=fetch) -> dict:
    """Ficha completa do mesmo id: gêneros, plataformas, lançamento, estúdios e resumo. Sem total de troféus (a IGDB não os tem)."""
    if not re.fullmatch(r'[0-9]{1,12}', external_id):
        raise ValueError('Identificador inválido para a IGDB.')
    body = (f'fields name,version_title,summary,url,cover.image_id,platforms.name,first_release_date,genres.name,'
            f'involved_companies.developer,involved_companies.publisher,involved_companies.company.name; where id = {int(external_id)};')
    games = _query(config, 'games', body, fetch)
    game = games[0] if games and isinstance(games[0], dict) else None
    if not game or not isinstance(game.get('name'), str):
        raise ValueError('Jogo não encontrado na IGDB.')
    cover = game.get('cover', {}).get('image_id') if isinstance(game.get('cover'), dict) else None
    developers, publishers = [], []
    for company in game.get('involved_companies', []) if isinstance(game.get('involved_companies'), list) else []:
        name = company.get('company', {}).get('name') if isinstance(company, dict) and isinstance(company.get('company'), dict) else None
        if not isinstance(name, str):
            continue
        if company.get('developer') and name not in developers:
            developers.append(name)
        if company.get('publisher') and name not in publishers:
            publishers.append(name)
    title = game['name'] + (f' ({game["version_title"]})' if isinstance(game.get('version_title'), str) and game['version_title'] else '')
    return {
        'titulo': title[:150], 'imagem': cover_url(cover) if isinstance(cover, str) and re.fullmatch(r'[a-z0-9]+', cover) else None,
        'origem': game.get('url') if isinstance(game.get('url'), str) and game['url'].startswith('https://www.igdb.com/') else f'https://www.igdb.com/games/{external_id}',
        'data_lancamento': _date(game.get('first_release_date')), 'ano': _year(game.get('first_release_date')),
        'plataformas': [p['name'] for p in game.get('platforms', []) if isinstance(p, dict) and isinstance(p.get('name'), str)][:8],
        'generos': [g['name'] for g in game.get('genres', []) if isinstance(g, dict) and isinstance(g.get('name'), str)][:8],
        'desenvolvedores': developers[:8], 'publicadoras': publishers[:8], 'descricao': game.get('summary') if isinstance(game.get('summary'), str) else '',
    }
