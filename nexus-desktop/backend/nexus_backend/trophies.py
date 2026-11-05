"""Sincronização opcional de troféus e conquistas por fontes oficiais, com chave pessoal guardada só neste computador.

Entram aqui apenas fontes com API pública documentada e permitida para uso pessoal:

- **Steam Web API** (Valve): chave pessoal de https://steamcommunity.com/dev/apikey + SteamID64. Exige "Detalhes do jogo"
  públicos na privacidade do perfil. Endpoints: IPlayerService/GetRecentlyPlayedGames, IPlayerService/GetOwnedGames e
  ISteamUserStats/GetPlayerAchievements (https://partner.steamgames.com/doc/webapi).
- **RetroAchievements**: chave de API web (Configurações → Keys em https://retroachievements.org/settings) + nome de usuário.
  Endpoints documentados em https://api-docs.retroachievements.org.

PlayStation, Xbox, Nintendo e Epic não têm API oficial para o usuário final e ficam de fora por decisão de segurança: as
bibliotecas não oficiais usam a sessão da conta, podem violar os termos de uso e levar a banimento.

As credenciais ficam em `steam-perfil-{id}.json` / `retroachievements-perfil-{id}.json` na pasta de dados do Nexus (uma por perfil): gravadas só a partir deste
computador, nunca devolvidas ao navegador, nunca em logs e fora do Git. Sem o arquivo, a fonte fica desligada e a
biblioteca segue com troféus manuais.
"""
from datetime import datetime, timezone
import http.client
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlencode

from . import covers
from .images import fetch as http_fetch

STEAM_API_HOSTS = {'api.steampowered.com'}
RETRO_HOSTS = {'retroachievements.org'}
RETRO_IMAGE_BASE = 'https://media.retroachievements.org'
MAX_JSON_BYTES = 4 * 1024 * 1024  # a lista de jogos possuídos de uma conta grande passa de 1 MB
TIMEOUT = 12
MAX_LIST = 300
MAX_IMPORT = 50
SOURCES = ('steam', 'retroachievements')
LABELS = {'steam': 'Steam', 'retroachievements': 'RetroAchievements'}
FILES = {'steam': 'steam.json', 'retroachievements': 'retroachievements.json'}
IDENTIFICATION_LABEL = {'steam': 'SteamID64', 'retroachievements': 'usuário'}
# Formatos aceitos: chave Web API da Steam (32 hexadecimais) + SteamID64 (17 dígitos iniciados por 7656119);
# chave web do RetroAchievements (alfanumérica) + nome de usuário ou ULID.
RULES = {
    'steam': {'api_key': re.compile(r'[A-Fa-f0-9]{32}'), 'identificacao': re.compile(r'7656119[0-9]{10}')},
    'retroachievements': {'api_key': re.compile(r'[A-Za-z0-9]{16,64}'), 'identificacao': re.compile(r'[A-Za-z0-9_-]{2,40}')},
}
FORMAT_HINTS = {
    'steam': ('A chave Web API da Steam tem 32 letras e números (0-9, A-F).', 'O SteamID64 tem 17 dígitos e começa por 7656119.'),
    'retroachievements': ('A chave de API web do RetroAchievements só tem letras e números.', 'Informe o nome de usuário do RetroAchievements (letras, números, _ ou -).'),
}
log = logging.getLogger('nexus.trofeus')


class SourceError(ValueError):
    """Falha explicável de uma fonte. `codigo`: credenciais, privado, sem_conquistas ou indisponivel."""
    def __init__(self, codigo: str, message: str, status: int = 0):
        super().__init__(message)
        self.codigo, self.status = codigo, status


# --- Credenciais locais ------------------------------------------------------------------------------------------------

def config_path(data_dir: Path, source: str, user_id: int) -> Path:
    """Um arquivo por perfil do Nexus: cada pessoa da casa vincula a própria conta (ex.: `steam-perfil-2.json`)."""
    return Path(data_dir) / FILES[source].replace('.json', f'-perfil-{int(user_id)}.json')


def load_config(data_dir: Path, source: str, user_id: int) -> dict | None:
    if source not in FILES:
        return None
    path = config_path(data_dir, source, user_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    values = {key: data.get(key, '') for key in ('api_key', 'identificacao')}
    if not all(isinstance(value, str) and RULES[source][key].fullmatch(value) for key, value in values.items()):
        return None
    return values


def validate(source: str, api_key: str, identificacao: str) -> dict:
    """Confere o formato antes de qualquer chamada de rede; a mensagem nunca repete o valor digitado."""
    if source not in RULES:
        raise ValueError('Fonte de troféus desconhecida.')
    api_key, identificacao = api_key.strip(), identificacao.strip()
    if not RULES[source]['api_key'].fullmatch(api_key):
        raise ValueError(FORMAT_HINTS[source][0])
    if not RULES[source]['identificacao'].fullmatch(identificacao):
        raise ValueError(FORMAT_HINTS[source][1])
    return {'api_key': api_key, 'identificacao': identificacao}


def save_config(data_dir: Path, source: str, user_id: int, config: dict) -> None:
    config_path(data_dir, source, user_id).write_text(json.dumps({'api_key': config['api_key'], 'identificacao': config['identificacao']}), encoding='utf-8')
    log.info('Fonte %s vinculada ao perfil %s neste computador (%s %s).', LABELS[source], user_id, IDENTIFICATION_LABEL[source], config['identificacao'])


def remove_config(data_dir: Path, source: str, user_id: int) -> bool:
    path = config_path(data_dir, source, user_id)
    if not path.is_file():
        return False
    path.unlink()
    log.info('Fonte %s desvinculada do perfil %s.', LABELS[source], user_id)
    return True


def status(data_dir: Path, source: str, user_id: int) -> dict:
    config = load_config(data_dir, source, user_id)
    return {'fonte': source, 'rotulo': LABELS[source], 'configurada': config is not None,
            'identificacao': config['identificacao'] if config else '', 'arquivo': str(config_path(data_dir, source, user_id))}


def all_status(data_dir: Path, user_id: int) -> dict:
    return {source: status(data_dir, source, user_id) for source in SOURCES}


def all_configs(data_dir: Path, user_id: int) -> dict[str, dict]:
    """Só as fontes vinculadas pelo perfil, prontas para `sync`."""
    configs = {source: load_config(data_dir, source, user_id) for source in SOURCES}
    return {source: config for source, config in configs.items() if config}


# --- HTTP ------------------------------------------------------------------------------------------------------------

def _json(url: str, hosts: set[str], fetch=None) -> object:
    """JSON de uma fonte; erros viram SourceError com mensagem genérica (a URL, que carrega a chave, nunca sai daqui)."""
    fetch = fetch or http_fetch  # resolvido na chamada, para os testes trocarem o transporte sem rede
    try:
        content_type, data = fetch(url, 'application/json', ('application/json', 'text/json'), MAX_JSON_BYTES, hosts, TIMEOUT)
    except ValueError as exc:
        match = re.search(r'HTTP ([0-9]{3})', str(exc))
        code = int(match.group(1)) if match else 0
        if code in (401, 403):
            raise SourceError('credenciais', 'A fonte recusou a consulta: confira a chave e a identificação informadas.', code) from exc
        if code == 429:
            raise SourceError('indisponivel', 'A fonte limitou as consultas por agora; tente de novo em alguns minutos.', code) from exc
        if code in (400, 404):
            raise SourceError('sem_conquistas', 'A fonte não tem esse registro.', code) from exc
        raise SourceError('indisponivel', 'A fonte não respondeu como esperado; tente de novo mais tarde.', code) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise SourceError('indisponivel', 'Não foi possível falar com a fonte; confira a conexão e tente de novo.') from exc
    try:
        return json.loads(data)
    except ValueError as exc:
        raise SourceError('indisponivel', 'Resposta inválida da fonte.') from exc


def _int(value, limit: int = 1000000) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if 0 <= value <= limit else 0
    if isinstance(value, str) and value.isdigit() and int(value) <= limit:
        return int(value)
    return 0


def _iso_day(stamp) -> str | None:
    return datetime.fromtimestamp(int(stamp), timezone.utc).date().isoformat() if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and stamp > 0 else None


def _text_day(value) -> str | None:
    return value[:10] if isinstance(value, str) and re.match(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) else None


def _item(source: str, external_id: str, title: str, image: str | None, preview: str | None, origin: str, platform: str, **extra) -> dict:
    """Jogo da conta, em formato fechado: só estes campos chegam ao navegador."""
    return {'fonte': source, 'id': external_id, 'titulo': title, 'imagem': image, 'previa': preview, 'origem': origin, 'plataforma': platform,
            'minutos': extra.get('minutos'), 'ultimo_jogo': extra.get('ultimo_jogo'),
            'trofeus_obtidos': extra.get('trofeus_obtidos'), 'trofeus_total': extra.get('trofeus_total')}


# --- Steam -----------------------------------------------------------------------------------------------------------

def _steam_url(method: str, config: dict, **params) -> str:
    return f'https://api.steampowered.com/{method}/?' + urlencode({'key': config['api_key'], 'steamid': config['identificacao'], 'format': 'json', **params})


def steam_games(config: dict, mode: str = 'recentes', fetch=None) -> list[dict]:
    """Jogos recentes (duas semanas) ou possuídos com tempo registrado; a Steam devolve vazio quando o perfil é privado."""
    try:
        if mode == 'recentes':
            result = _json(_steam_url('IPlayerService/GetRecentlyPlayedGames/v1', config, count=100), STEAM_API_HOSTS, fetch)
            marker = 'total_count'
        else:
            result = _json(_steam_url('IPlayerService/GetOwnedGames/v1', config, include_appinfo=1, include_played_free_games=1), STEAM_API_HOSTS, fetch)
            marker = 'game_count'
    except SourceError as exc:
        if exc.codigo == 'credenciais':
            raise SourceError('credenciais', 'A Steam recusou a chave Web API. Confira se copiou a chave inteira de steamcommunity.com/dev/apikey.', exc.status) from exc
        raise
    response = result.get('response') if isinstance(result, dict) and isinstance(result.get('response'), dict) else None
    if response is None or (marker not in response and not response.get('games')):
        raise SourceError('privado', 'A Steam não devolveu a lista de jogos: confira o SteamID64 e deixe "Detalhes do jogo" público na privacidade do perfil.')
    items = []
    for game in response.get('games') or []:
        if not isinstance(game, dict) or not isinstance(game.get('appid'), int) or isinstance(game.get('appid'), bool) or game['appid'] <= 0 or not isinstance(game.get('name'), str):
            continue
        minutes = _int(game.get('playtime_forever'), 100000000)
        if mode == 'possuidos' and minutes == 0:
            continue  # possuído mas nunca aberto: não é parte da jornada
        app_id = str(game['appid'])
        items.append(_item('steam', app_id, covers._text(game['name'], 150) or f'Steam {app_id}', covers.steam_image(app_id), covers.steam_image(app_id),
                           f'https://store.steampowered.com/app/{app_id}/', 'PC', minutos=minutes, ultimo_jogo=_iso_day(game.get('rtime_last_played'))))
    if mode != 'recentes':
        items.sort(key=lambda item: (item['ultimo_jogo'] or '', item['minutos']), reverse=True)
    return items[:MAX_LIST]


def steam_achievements(config: dict, app_id: str, fetch=None) -> dict:
    """Obtidas e total do jogo base para a conta vinculada; jogo sem conquistas e perfil privado viram erros explicáveis."""
    if not re.fullmatch(r'[0-9]{1,10}', app_id):
        raise SourceError('indisponivel', 'Identificador inválido para a Steam.')
    try:
        result = _json(_steam_url('ISteamUserStats/GetPlayerAchievements/v1', config, appid=app_id, l='portuguese'), STEAM_API_HOSTS, fetch)
    except SourceError as exc:
        if exc.status == 400:
            raise SourceError('sem_conquistas', 'Este jogo não tem conquistas na Steam.', 400) from exc
        if exc.status == 403:
            raise SourceError('privado', 'A Steam recusou: a chave é inválida ou o perfil não tem "Detalhes do jogo" públicos.', 403) from exc
        raise
    stats = result.get('playerstats') if isinstance(result, dict) and isinstance(result.get('playerstats'), dict) else {}
    achievements = [entry for entry in (stats.get('achievements') if isinstance(stats.get('achievements'), list) else []) if isinstance(entry, dict)]
    if not stats.get('success') or not achievements:
        raise SourceError('sem_conquistas', 'Este jogo não tem conquistas na Steam.')
    return {'obtidos': sum(1 for entry in achievements if entry.get('achieved') == 1), 'total': len(achievements), 'escopo': 'jogo base'}


# --- RetroAchievements -------------------------------------------------------------------------------------------------

def _retro_url(endpoint: str, config: dict, **params) -> str:
    return f'https://retroachievements.org/API/{endpoint}.php?' + urlencode({'y': config['api_key'], 'u': config['identificacao'], **params})


def _retro_image(path) -> str | None:
    """Só caminhos de imagem do próprio site, em PNG/JPEG (os ícones GIF animados não servem de capa)."""
    if isinstance(path, str) and re.fullmatch(r'/Images/[0-9]{1,8}\.(png|jpg|jpeg)', path, re.I) and path != '/Images/000001.png':
        return RETRO_IMAGE_BASE + path
    return None


def _retro_call(endpoint: str, config: dict, fetch, **params) -> object:
    try:
        return _json(_retro_url(endpoint, config, **params), RETRO_HOSTS, fetch)
    except SourceError as exc:
        if exc.codigo == 'credenciais':
            raise SourceError('credenciais', 'O RetroAchievements recusou a chave de API web ou o nome de usuário.', exc.status) from exc
        raise


def retro_games(config: dict, mode: str = 'recentes', fetch=None) -> list[dict]:
    """Jogos recentes ou todos com algum progresso na conta, já com obtidas/total do conjunto de conquistas."""
    if mode == 'recentes':
        result = _retro_call('API_GetUserRecentlyPlayedGames', config, fetch, c=50, o=0)
        rows = result if isinstance(result, list) else []
    else:
        result = _retro_call('API_GetUserCompletionProgress', config, fetch, c=500, o=0)
        rows = result.get('Results') if isinstance(result, dict) and isinstance(result.get('Results'), list) else []
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        game_id = _int(row.get('GameID'), 10 ** 9)
        title = covers._text(row.get('Title'), 150)
        if game_id <= 0 or not title:
            continue
        total = _int(row.get('NumPossibleAchievements', row.get('MaxPossible')))
        earned = max(_int(row.get('NumAchieved', row.get('NumAwarded'))), _int(row.get('NumAchievedHardcore', row.get('NumAwardedHardcore'))))
        icon, box = _retro_image(row.get('ImageIcon')), _retro_image(row.get('ImageBoxArt'))
        items.append(_item('retroachievements', str(game_id), title, box or icon, icon or box, f'https://retroachievements.org/game/{game_id}',
                           covers._text(row.get('ConsoleName'), 30) or 'Outro', ultimo_jogo=_text_day(row.get('LastPlayed') or row.get('MostRecentAwardedDate')),
                           trofeus_obtidos=min(earned, total) if total else None, trofeus_total=total or None))
    return items[:MAX_LIST]


def retro_progress(config: dict, ids: list[str], fetch=None) -> dict[str, dict]:
    """Obtidas/total de vários jogos numa chamada só (lotes de 50); jogos sem conjunto de conquistas ficam de fora."""
    results: dict[str, dict] = {}
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        result = _retro_call('API_GetUserProgress', config, fetch, i=','.join(chunk))
        for game_id in chunk:
            entry = result.get(game_id) if isinstance(result, dict) else None
            if not isinstance(entry, dict):
                continue
            total = _int(entry.get('NumPossibleAchievements'))
            earned = max(_int(entry.get('NumAchieved')), _int(entry.get('NumAchievedHardcore')))
            if total > 0:
                results[game_id] = {'obtidos': min(earned, total), 'total': total, 'escopo': 'jogo base'}
    return results


def retro_details(config: dict, game_id: str, fetch=None) -> dict:
    """Ficha do jogo (console, estúdio, publicadora, gênero, lançamento e capa) no mesmo formato fechado das outras fontes."""
    if not re.fullmatch(r'[0-9]{1,9}', game_id):
        raise ValueError('Identificador inválido para o RetroAchievements.')
    result = _retro_call('API_GetGame', config, fetch, i=game_id)
    title = covers._text(result.get('Title'), 150) if isinstance(result, dict) else ''
    if not title:
        raise SourceError('sem_conquistas', 'Jogo não encontrado no RetroAchievements.')
    released, day, year = result.get('Released'), None, None
    match = re.match(r'([0-9]{4})(-[0-9]{2}-[0-9]{2})?', released) if isinstance(released, str) else None
    if match:
        year = int(match.group(1))
        day = match.group(0) if match.group(2) else None
    console = covers._text(result.get('ConsoleName'), 30)
    genres = [part.strip() for part in result['Genre'].split(',')] if isinstance(result.get('Genre'), str) else []
    return covers._details('retroachievements', game_id, title, _retro_image(result.get('ImageBoxArt')) or _retro_image(result.get('ImageTitle')),
                           f'https://retroachievements.org/game/{game_id}', data_lancamento=day, ano=year, plataformas=[console] if console else [],
                           generos=covers._strings(genres), desenvolvedores=covers._strings([result.get('Developer')]),
                           publicadoras=covers._strings([result.get('Publisher')]), descricao='', fundo=_retro_image(result.get('ImageIngame')) or _retro_image(result.get('ImageTitle')))


# --- Fachada comum -----------------------------------------------------------------------------------------------------

def list_games(source: str, config: dict, mode: str = 'recentes', fetch=None) -> list[dict]:
    if source == 'steam':
        return steam_games(config, mode, fetch)
    if source == 'retroachievements':
        return retro_games(config, mode, fetch)
    raise ValueError('Fonte de troféus desconhecida.')


def progress(source: str, config: dict, ids: list[str], fetch=None) -> dict[str, dict | SourceError]:
    """Obtidas/total por identificador externo; cada falha fica registrada no lugar do resultado, sem interromper os demais."""
    if source == 'retroachievements':
        try:
            found = retro_progress(config, ids, fetch)
        except SourceError as exc:
            return {game_id: exc for game_id in ids}
        return {game_id: found.get(game_id) or SourceError('sem_conquistas', 'Sem conjunto de conquistas para este jogo no RetroAchievements.') for game_id in ids}
    results: dict[str, dict | SourceError] = {}
    for index, app_id in enumerate(ids):
        try:
            results[app_id] = steam_achievements(config, app_id, fetch)
        except SourceError as exc:
            results[app_id] = exc
            if exc.codigo in ('privado', 'credenciais', 'indisponivel'):
                # Repetir não muda o resultado e gastaria o limite da chave: os demais recebem o mesmo motivo.
                for rest in ids[index + 1:]:
                    results[rest] = exc
                break
    return results


def sync(conn, user_id: int, configs: dict[str, dict], game_id: int | None = None, fetch=None) -> dict:
    """Atualiza obtidas/total dos jogos ligados a fontes vinculadas. Consulta tudo antes de gravar; nunca zera valores por falha."""
    query = "SELECT id,nome,fonte_externa,id_externo,trofeus_obtidos,trofeus_total FROM jogos WHERE usuario_id=? AND fonte_externa IN ('steam','retroachievements') AND id_externo<>''"
    params: list = [user_id]
    if game_id is not None:
        query += ' AND id=?'
        params.append(game_id)
    rows = [dict(row) for row in conn.execute(query + ' ORDER BY posicao,id', params)]
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    updated, skipped, writes = [], [], []
    for source in SOURCES:
        mine = [row for row in rows if row['fonte_externa'] == source]
        if not mine:
            continue
        config = configs.get(source)
        if not config:
            skipped.extend({'id': row['id'], 'nome': row['nome'], 'motivo': f'{LABELS[source]} não está vinculada neste computador.'} for row in mine)
            continue
        results = progress(source, config, list(dict.fromkeys(row['id_externo'] for row in mine)), fetch)
        for row in mine:
            result = results.get(row['id_externo'])
            if not isinstance(result, dict):
                skipped.append({'id': row['id'], 'nome': row['nome'], 'motivo': str(result) if result else 'Sem resposta da fonte.'})
                continue
            writes.append((result['obtidos'], result['total'], source, result['escopo'], stamp, row['id'], user_id))
            updated.append({'id': row['id'], 'nome': row['nome'], 'antes': {'obtidos': row['trofeus_obtidos'], 'total': row['trofeus_total']},
                            'obtidos': result['obtidos'], 'total': result['total'], 'mudou': (row['trofeus_obtidos'], row['trofeus_total']) != (result['obtidos'], result['total'])})
    if writes:
        conn.executemany("UPDATE jogos SET trofeus_obtidos=?, trofeus_total=?, trofeus_fonte=?, trofeus_escopo=?, trofeus_consultado_em=?, "
                         "atualizado=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND usuario_id=?", writes)
    return {'atualizados': updated, 'ignorados': skipped, 'consultado_em': stamp, 'total': len(rows)}


# --- Lista de conquistas de um jogo (visualizador) ----------------------------------------------------------------------

STEAM_ICON_HOSTS = covers.STEAM_IMAGE_HOSTS | {'steamcdn-a.akamaihd.net', 'media.steampowered.com'}


def _icon(url, hosts: set[str]) -> str | None:
    return url if isinstance(url, str) and covers._image_allowed(url, hosts) else None


def _achievement(identifier: str, name: str, description: str, earned: bool, earned_at: str | None, icon: str | None,
                 locked_icon: str | None, rarity: float | None, hidden: bool = False, points: int | None = None) -> dict:
    """Uma conquista em formato fechado: só estes campos chegam ao navegador."""
    return {'id': identifier[:120], 'nome': name[:150] or identifier[:150], 'descricao': description[:500], 'oculta': hidden, 'obtida': earned,
            'obtida_em': earned_at, 'icone': icon, 'icone_bloqueado': locked_icon, 'raridade': rarity, 'pontos': points}


def _cached(cache, key: str, loader):
    if cache is not None and (hit := cache.get(key)) is not None:
        return hit
    value = loader()
    if cache is not None:
        cache.set(key, value)
    return value


def _stamp_from_epoch(stamp) -> str | None:
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) and stamp > 0:
        return datetime.fromtimestamp(int(stamp), timezone.utc).isoformat(timespec='seconds')
    return None


def steam_achievement_list(config: dict, app_id: str, fetch=None, cache=None) -> dict:
    """Conquistas do jogo com o estado do jogador; esquema (nomes, ícones, ocultas) e raridade global ficam em cache, o estado não."""
    if not re.fullmatch(r'[0-9]{1,10}', app_id):
        raise SourceError('indisponivel', 'Identificador inválido para a Steam.')
    try:
        player = _json(_steam_url('ISteamUserStats/GetPlayerAchievements/v1', config, appid=app_id, l='portuguese'), STEAM_API_HOSTS, fetch)
    except SourceError as exc:
        if exc.status == 400:
            raise SourceError('sem_conquistas', 'Este jogo não tem conquistas na Steam.', 400) from exc
        if exc.status == 403:
            raise SourceError('privado', 'A Steam recusou: a chave é inválida ou o perfil não tem "Detalhes do jogo" públicos.', 403) from exc
        raise
    stats = player.get('playerstats') if isinstance(player, dict) and isinstance(player.get('playerstats'), dict) else {}
    entries = [entry for entry in (stats.get('achievements') if isinstance(stats.get('achievements'), list) else []) if isinstance(entry, dict) and isinstance(entry.get('apiname'), str)]
    if not stats.get('success') or not entries:
        raise SourceError('sem_conquistas', 'Este jogo não tem conquistas na Steam.')

    def load_schema():
        result = _json(_steam_url('ISteamUserStats/GetSchemaForGame/v2', config, appid=app_id, l='portuguese'), STEAM_API_HOSTS, fetch)
        game = result.get('game') if isinstance(result, dict) and isinstance(result.get('game'), dict) else {}
        block = game.get('availableGameStats') if isinstance(game.get('availableGameStats'), dict) else {}
        rows = block.get('achievements') if isinstance(block.get('achievements'), list) else []
        return {row['name']: row for row in rows if isinstance(row, dict) and isinstance(row.get('name'), str)}

    def load_rarity():
        try:
            result = _json(f'https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/?gameid={app_id}', STEAM_API_HOSTS, fetch)
        except SourceError:
            return {}
        block = result.get('achievementpercentages') if isinstance(result, dict) and isinstance(result.get('achievementpercentages'), dict) else {}
        rarity = {}
        for row in block.get('achievements') if isinstance(block.get('achievements'), list) else []:
            if isinstance(row, dict) and isinstance(row.get('name'), str):
                try:
                    rarity[row['name']] = round(float(row.get('percent')), 1)
                except (TypeError, ValueError):
                    continue
        return rarity

    schema = _cached(cache, f'steam-esquema-{app_id}', load_schema)
    rarity = _cached(cache, f'steam-raridade-{app_id}', load_rarity)
    order = {name: index for index, name in enumerate(schema)}
    items = []
    for entry in sorted(entries, key=lambda e: order.get(e['apiname'], len(order))):
        meta = schema.get(entry['apiname'], {})
        earned = entry.get('achieved') == 1
        items.append(_achievement(entry['apiname'], covers._text(meta.get('displayName') or entry.get('name'), 150), covers._text(meta.get('description') or entry.get('description'), 500),
                                  earned, _stamp_from_epoch(entry.get('unlocktime')) if earned else None, _icon(meta.get('icon'), STEAM_ICON_HOSTS),
                                  _icon(meta.get('icongray'), STEAM_ICON_HOSTS), rarity.get(entry['apiname']), hidden=meta.get('hidden') == 1))
    return {'itens': items, 'obtidos': sum(1 for item in items if item['obtida']), 'total': len(items), 'escopo': 'jogo base', 'titulo': covers._text(stats.get('gameName'), 150)}


def retro_achievement_list(config: dict, game_id: str, fetch=None) -> dict:
    """Conquistas do conjunto com o progresso do usuário (API_GetGameInfoAndUserProgress), na ordem de exibição do site."""
    if not re.fullmatch(r'[0-9]{1,9}', game_id):
        raise SourceError('indisponivel', 'Identificador inválido para o RetroAchievements.')
    result = _retro_call('API_GetGameInfoAndUserProgress', config, fetch, g=game_id, a=1)
    if not isinstance(result, dict):
        raise SourceError('indisponivel', 'Resposta inválida do RetroAchievements.')
    rows = result.get('Achievements')
    rows = list(rows.values()) if isinstance(rows, dict) else rows if isinstance(rows, list) else []
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        raise SourceError('sem_conquistas', 'Este jogo não tem conjunto de conquistas no RetroAchievements.')
    players = _int(result.get('NumDistinctPlayers', result.get('NumDistinctPlayersCasual')), 10 ** 9)
    items = []
    for row in sorted(rows, key=lambda r: _int(r.get('DisplayOrder'), 10 ** 6)):
        badge = row.get('BadgeName')
        badge = badge if isinstance(badge, str) and re.fullmatch(r'[0-9]{1,9}', badge) else None
        raw_date = row.get('DateEarnedHardcore') or row.get('DateEarned')
        earned_at = None
        if isinstance(raw_date, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}', raw_date):
            earned_at = raw_date.replace(' ', 'T') + '+00:00'
        elif _text_day(raw_date):
            earned_at = _text_day(raw_date)
        awarded = _int(row.get('NumAwarded'), 10 ** 9)
        items.append(_achievement(str(_int(row.get('ID'), 10 ** 9)), covers._text(row.get('Title'), 150), covers._text(row.get('Description'), 500), earned_at is not None, earned_at,
                                  f'{RETRO_IMAGE_BASE}/Badge/{badge}.png' if badge else None, f'{RETRO_IMAGE_BASE}/Badge/{badge}_lock.png' if badge else None,
                                  round(awarded * 100 / players, 1) if players and awarded else None, points=_int(row.get('Points'), 10000) or None))
    return {'itens': items, 'obtidos': sum(1 for item in items if item['obtida']), 'total': len(items), 'escopo': 'jogo base', 'titulo': covers._text(result.get('Title'), 150)}


def achievement_list(source: str, config: dict, external_id: str, fetch=None, cache=None) -> dict:
    if source == 'steam':
        return steam_achievement_list(config, external_id, fetch, cache)
    if source == 'retroachievements':
        return retro_achievement_list(config, external_id, fetch)
    raise ValueError('Fonte de troféus desconhecida.')


def record_counts(conn, user_id: int, game_id: int, source: str, earned: int, total: int, scope: str = 'jogo base') -> str:
    """Grava obtidos/total vindos da fonte no jogo (mesma regra da sincronização) e devolve a data da consulta."""
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    conn.execute("UPDATE jogos SET trofeus_obtidos=?, trofeus_total=?, trofeus_fonte=?, trofeus_escopo=?, trofeus_consultado_em=?, "
                 "atualizado=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND usuario_id=?", (min(earned, total), total, source, scope, stamp, game_id, user_id))
    return stamp
