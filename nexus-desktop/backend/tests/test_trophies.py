"""Troféus por fontes oficiais (Steam Web API e RetroAchievements): vínculo local, listas da conta, importação e sincronização."""
import json
import pytest
from fastapi.testclient import TestClient
from nexus_backend import covers, trophies
from nexus_backend.api import create_app
from tests.test_api import image_bytes, profile

STEAM = {'api_key': 'ABCDEF0123456789ABCDEF0123456789', 'identificacao': '76561198000000001'}
RETRO = {'api_key': 'ChaveRetro1234567890', 'identificacao': 'kiba_wolf'}
RECENT = {'response': {'total_count': 2, 'games': [
    {'appid': 1091500, 'name': 'Cyberpunk 2077', 'playtime_2weeks': 300, 'playtime_forever': 5400},
    {'appid': 108600, 'name': 'Project Zomboid', 'playtime_2weeks': 20, 'playtime_forever': 90}, {'appid': 'x', 'name': 'inválido'}]}}
OWNED = {'response': {'game_count': 3, 'games': [
    {'appid': 1091500, 'name': 'Cyberpunk 2077', 'playtime_forever': 5400, 'rtime_last_played': 1760000000},
    {'appid': 620, 'name': 'Portal 2', 'playtime_forever': 0}, {'appid': 440, 'name': 'Team Fortress 2', 'playtime_forever': 12, 'rtime_last_played': 1770000000}]}}
ACHIEVEMENTS = {'playerstats': {'success': True, 'achievements': [{'apiname': 'a', 'achieved': 1}, {'apiname': 'b', 'achieved': 0}, {'apiname': 'c', 'achieved': 1}]}}
APPDETAILS = {'1091500': {'success': True, 'data': {'name': 'Cyberpunk 2077', 'genres': [{'description': 'RPG'}], 'release_date': {'date': '10 dez. 2020'},
                                                   'developers': ['CD PROJEKT RED'], 'publishers': ['CD PROJEKT RED'], 'platforms': {'windows': True}, 'short_description': 'Night City.',
                                                   'achievements': {'total': 3}}}}
RETRO_RECENT = [{'GameID': 11240, 'Title': 'Super Mario World', 'ConsoleName': 'SNES/Super Famicom', 'ImageIcon': '/Images/012345.png', 'ImageBoxArt': '/Images/099999.jpg',
                 'LastPlayed': '2026-10-20 21:00:00', 'NumPossibleAchievements': 50, 'NumAchieved': 12, 'NumAchievedHardcore': 10},
                {'GameID': 'abc', 'Title': 'ruim'}, {'GameID': 2, 'Title': 'Sem imagem', 'ConsoleName': 'Mega Drive', 'ImageIcon': '/Images/000001.png', 'NumPossibleAchievements': 0}]
RETRO_PROGRESS = {'11240': {'NumPossibleAchievements': 50, 'NumAchieved': 13, 'NumAchievedHardcore': 11}, '2': {'NumPossibleAchievements': 0}}
RETRO_GAME = {'Title': 'Super Mario World', 'ConsoleName': 'SNES/Super Famicom', 'ImageBoxArt': '/Images/099999.jpg', 'Developer': 'Nintendo EAD', 'Publisher': 'Nintendo',
              'Genre': 'Plataforma, Aventura', 'Released': '1990-11-21'}


def transport(responses, fail=None):
    """Transporte simulado com a assinatura de images.fetch; devolve JSON ou imagem conforme a URL e registra as chamadas."""
    calls = []

    def fetch(url, accept, content_types, max_bytes, allowed_hosts=None, seconds=25, method='GET', body=None, headers=None):
        calls.append((url, allowed_hosts))
        for prefix, status in (fail or {}).items():
            if url.startswith(prefix):
                raise ValueError(f'O servidor respondeu HTTP {status}.')
        if url.endswith('.jpg') or url.endswith('.png'):
            return 'image/png', image_bytes()
        for prefix, value in responses.items():
            if url.startswith(prefix):
                return 'application/json', json.dumps(value).encode()
        raise AssertionError('URL inesperada: ' + url)
    fetch.calls = calls
    return fetch


def test_credentials_are_checked_by_format_stored_locally_and_never_echoed(tmp_path):
    with pytest.raises(ValueError, match='32 letras'):
        trophies.validate('steam', 'curta', STEAM['identificacao'])
    with pytest.raises(ValueError, match='7656119'):
        trophies.validate('steam', STEAM['api_key'], '12345')
    with pytest.raises(ValueError, match='letras e números'):
        trophies.validate('retroachievements', 'chave com espaço', 'kiba')
    assert trophies.load_config(tmp_path, 'steam', 1) is None and trophies.status(tmp_path, 'steam', 1)['configurada'] is False
    trophies.save_config(tmp_path, 'steam', 1, trophies.validate('steam', ' ' + STEAM['api_key'] + ' ', STEAM['identificacao']))
    assert trophies.load_config(tmp_path, 'steam', 1) == STEAM and trophies.load_config(tmp_path, 'steam', 2) is None, 'one link per profile'
    status = trophies.status(tmp_path, 'steam', 1)
    assert status['configurada'] and status['identificacao'] == STEAM['identificacao'] and 'api_key' not in status
    (tmp_path / 'steam-perfil-1.json').write_text('{"api_key": "zz", "identificacao": "76561198000000001"}', encoding='utf-8')
    assert trophies.load_config(tmp_path, 'steam', 1) is None, 'a malformed file switches the source off instead of sending junk to the network'
    assert trophies.remove_config(tmp_path, 'steam', 1) is True and trophies.remove_config(tmp_path, 'steam', 1) is False


def test_steam_lists_recent_and_owned_games_and_reads_achievements():
    fetch = transport({'https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames': RECENT, 'https://api.steampowered.com/IPlayerService/GetOwnedGames': OWNED,
                       'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements': ACHIEVEMENTS})
    recent = trophies.steam_games(STEAM, 'recentes', fetch)
    assert [item['id'] for item in recent] == ['1091500', '108600'] and recent[0]['minutos'] == 5400 and recent[0]['plataforma'] == 'PC'
    assert recent[0]['imagem'].startswith(covers.STEAM_IMAGE_BASE) and recent[0]['origem'] == 'https://store.steampowered.com/app/1091500/'
    assert fetch.calls[0][1] == trophies.STEAM_API_HOSTS and 'key=' + STEAM['api_key'] in fetch.calls[0][0] and 'steamid=76561198000000001' in fetch.calls[0][0]
    owned = trophies.steam_games(STEAM, 'possuidos', fetch)
    assert [item['id'] for item in owned] == ['440', '1091500'], 'never-played games drop out; most recently played first'
    assert owned[0]['ultimo_jogo'] == '2026-02-02'
    assert trophies.steam_achievements(STEAM, '1091500', fetch) == {'obtidos': 2, 'total': 3, 'escopo': 'jogo base'}
    private = transport({'https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames': {'response': {}}})
    with pytest.raises(trophies.SourceError) as caught:
        trophies.steam_games(STEAM, 'recentes', private)
    assert caught.value.codigo == 'privado' and 'Detalhes do jogo' in str(caught.value)
    refused = transport({}, fail={'https://api.steampowered.com/': 403})
    with pytest.raises(trophies.SourceError) as caught:
        trophies.steam_games(STEAM, 'recentes', refused)
    assert caught.value.codigo == 'credenciais' and STEAM['api_key'] not in str(caught.value)
    with pytest.raises(trophies.SourceError) as caught:
        trophies.steam_achievements(STEAM, '620', transport({}, fail={'https://api.steampowered.com/': 400}))
    assert caught.value.codigo == 'sem_conquistas'
    results = trophies.progress('steam', STEAM, ['1091500', '620'], refused)
    assert all(isinstance(r, trophies.SourceError) for r in results.values()) and len(refused.calls) == 2, 'a refused key stops the loop instead of burning the quota'


def test_retroachievements_lists_progress_and_details():
    fetch = transport({'https://retroachievements.org/API/API_GetUserRecentlyPlayedGames.php': RETRO_RECENT, 'https://retroachievements.org/API/API_GetUserProgress.php': RETRO_PROGRESS,
                       'https://retroachievements.org/API/API_GetGame.php': RETRO_GAME})
    items = trophies.retro_games(RETRO, 'recentes', fetch)
    assert [item['id'] for item in items] == ['11240', '2'] and items[0]['plataforma'] == 'SNES/Super Famicom' and items[0]['ultimo_jogo'] == '2026-10-20'
    assert items[0]['imagem'] == 'https://media.retroachievements.org/Images/099999.jpg' and items[0]['previa'] == 'https://media.retroachievements.org/Images/012345.png'
    assert items[0]['trofeus_obtidos'] == 12 and items[0]['trofeus_total'] == 50
    assert items[1]['imagem'] is None and items[1]['trofeus_total'] is None, 'placeholder icon and empty sets are not used'
    assert 'y=' + RETRO['api_key'] in fetch.calls[0][0] and 'u=kiba_wolf' in fetch.calls[0][0] and fetch.calls[0][1] == trophies.RETRO_HOSTS
    progress = trophies.progress('retroachievements', RETRO, ['11240', '2'], fetch)
    assert progress['11240'] == {'obtidos': 13, 'total': 50, 'escopo': 'jogo base'} and isinstance(progress['2'], trophies.SourceError)
    assert 'i=11240%2C2' in fetch.calls[-1][0], 'one batched call for every id'
    details = trophies.retro_details(RETRO, '11240', fetch)
    assert details['fonte'] == 'retroachievements' and details['titulo'] == 'Super Mario World' and details['data_lancamento'] == '1990-11-21' and details['ano'] == 1990
    assert details['desenvolvedores'] == ['Nintendo EAD'] and details['generos'] == ['Plataforma', 'Aventura'] and details['genero'] == 'Aventura'
    assert details['imagem'] == 'https://media.retroachievements.org/Images/099999.jpg' and details['trofeus_total'] is None
    with pytest.raises(trophies.SourceError) as caught:
        trophies.retro_games(RETRO, 'recentes', transport({}, fail={'https://retroachievements.org/': 401}))
    assert caught.value.codigo == 'credenciais' and 'RetroAchievements' in str(caught.value)


def test_api_links_imports_and_syncs_only_from_this_computer(tmp_path, monkeypatch):
    responses = {'https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames': RECENT, 'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements': ACHIEVEMENTS,
                 'https://store.steampowered.com/api/appdetails': APPDETAILS, 'https://retroachievements.org/API/API_GetUserRecentlyPlayedGames.php': RETRO_RECENT,
                 'https://retroachievements.org/API/API_GetUserProgress.php': RETRO_PROGRESS, 'https://retroachievements.org/API/API_GetGame.php': RETRO_GAME}
    fetch = transport(responses)
    monkeypatch.setattr(trophies, 'http_fetch', fetch)
    monkeypatch.setattr(covers, 'fetch', fetch)
    app = create_app(tmp_path)
    with TestClient(app, client=('192.168.15.50', 5000)) as phone, TestClient(app, client=('127.0.0.1', 5000)) as local:
        _, headers = profile(local)
        _, other = profile(local, 'Juan')
        assert local.get('/api/trofeus/fontes').status_code == 401
        sources = local.get('/api/trofeus/fontes', headers=headers).json()
        assert sources['local'] is True and sources['fontes']['steam']['configurada'] is False and sources['fontes']['retroachievements']['rotulo'] == 'RetroAchievements'
        assert phone.put('/api/trofeus/fontes/steam', headers=headers, json={'api_key': STEAM['api_key'], 'identificacao': STEAM['identificacao']}).status_code == 403
        assert local.put('/api/trofeus/fontes/steam', headers=headers, json={'api_key': 'curta', 'identificacao': STEAM['identificacao']}).status_code == 422
        assert local.get('/api/trofeus/steam/jogos', headers=headers).status_code == 409, 'nothing linked yet'
        linked = local.put('/api/trofeus/fontes/steam', headers=headers, json={'api_key': STEAM['api_key'], 'identificacao': STEAM['identificacao']})
        assert linked.status_code == 200 and linked.json()['configurada'] and 'api_key' not in linked.json() and (tmp_path / 'steam-perfil-1.json').is_file()
        assert local.get('/api/trofeus/fontes', headers=other).json()['fontes']['steam']['configurada'] is False, 'the other profile links its own account'
        assert local.get('/api/trofeus/steam/jogos', headers=other).status_code == 409
        assert local.put('/api/trofeus/fontes/retroachievements', headers=headers, json={'api_key': RETRO['api_key'], 'identificacao': RETRO['identificacao']}).status_code == 200
        assert phone.get('/api/trofeus/fontes', headers=headers).json()['local'] is False

        listed = local.get('/api/trofeus/steam/jogos', headers=headers).json()
        assert [item['id'] for item in listed['itens']] == ['1091500', '108600'] and listed['itens'][0]['na_biblioteca'] is None
        result = local.post('/api/trofeus/steam/importar', headers=headers, json={'ids': ['1091500', '999']})
        assert result.status_code == 201, result.text
        assert [g['nome'] for g in result.json()['importados']] == ['Cyberpunk 2077'] and result.json()['importados'][0]['capa'] and result.json()['importados'][0]['trofeus']
        assert result.json()['ignorados'][0]['id'] == '999' and 'lista da sua conta' in result.json()['ignorados'][0]['motivo']
        game = local.get(f'/api/jogos/{result.json()["importados"][0]["id"]}', headers=headers).json()
        assert game['fonte_externa'] == 'steam' and game['id_externo'] == '1091500' and game['minutos_jogados'] == 5400 and game['capa_id']
        assert game['trofeus_obtidos'] == 2 and game['trofeus_total'] == 3 and game['trofeus_fonte'] == 'steam' and game['genero'] == 'RPG' and game['desenvolvedor'] == 'CD PROJEKT RED'
        assert game['progresso'] == 0 and game['notas'] == '' and game['data_inicio'] is None, 'personal fields stay untouched'
        assert local.get('/api/trofeus/steam/jogos', headers=headers).json()['itens'][0]['na_biblioteca']['id'] == game['id']
        again = local.post('/api/trofeus/steam/importar', headers=headers, json={'ids': ['1091500']}).json()
        assert again['importados'] == [] and 'Já está na biblioteca' in again['ignorados'][0]['motivo']

        retro = local.post('/api/trofeus/retroachievements/importar', headers=headers, json={'ids': ['11240']}).json()
        mario = local.get(f'/api/jogos/{retro["importados"][0]["id"]}', headers=headers).json()
        assert mario['plataforma'] == 'SNES/Super Famicom' and mario['trofeus_obtidos'] == 12 and mario['trofeus_total'] == 50 and mario['publicadora'] == 'Nintendo' and mario['capa_id']

        manual = local.post('/api/jogos', headers=headers, json={'nome': 'Manual', 'trofeus_obtidos': 4, 'trofeus_total': 9}).json()
        synced = local.post('/api/trofeus/sincronizar', headers=headers, json={}).json()
        assert synced['total'] == 2 and {u['nome']: (u['obtidos'], u['total']) for u in synced['atualizados']} == {'Cyberpunk 2077': (2, 3), 'Super Mario World': (13, 50)}
        assert [u['mudou'] for u in synced['atualizados']] == [False, True]
        assert local.get(f'/api/jogos/{mario["id"]}', headers=headers).json()['trofeus_obtidos'] == 13
        assert local.get(f'/api/jogos/{manual["id"]}', headers=headers).json()['trofeus_obtidos'] == 4, 'manual games are not part of the sync'

        monkeypatch.setattr(trophies, 'http_fetch', transport(responses, fail={'https://api.steampowered.com/ISteamUserStats': 403}))
        failed = local.post('/api/trofeus/sincronizar', headers=headers, json={'jogo_id': game['id']}).json()
        assert failed['atualizados'] == [] and 'Detalhes do jogo' in failed['ignorados'][0]['motivo']
        assert local.get(f'/api/jogos/{game["id"]}', headers=headers).json()['trofeus_obtidos'] == 2, 'a failure keeps the previous values'
        assert local.post('/api/trofeus/sincronizar', headers=headers, json={'jogo_id': 999}).status_code == 404

        assert phone.delete('/api/trofeus/fontes/steam', headers=headers).status_code == 403
        assert local.delete('/api/trofeus/fontes/steam', headers=headers).status_code == 204 and not (tmp_path / 'steam-perfil-1.json').exists()
        assert local.delete('/api/trofeus/fontes/retroachievements', headers=headers).status_code == 204
        assert local.post('/api/trofeus/sincronizar', headers=headers, json={}).status_code == 409
        assert all(STEAM['api_key'] not in call[0] or call[1] == trophies.STEAM_API_HOSTS for call in fetch.calls), 'the key only ever travels to the Steam API host'


def test_igdb_candidates_can_be_applied_like_the_other_sources(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        _, headers = profile(client)
        response = client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'igdb', 'id': '1942'})
        assert response.status_code == 404 and 'IGDB não configurada' in response.text, 'accepted by validation; refused only because there is no local key'


SCHEMA = {'game': {'gameName': 'Cyberpunk 2077', 'availableGameStats': {'achievements': [
    {'name': 'a', 'displayName': 'O Começo', 'hidden': 0, 'description': 'Termine o prólogo.', 'icon': 'https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/1091500/a.jpg', 'icongray': 'https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/1091500/a_gray.jpg'},
    {'name': 'b', 'displayName': 'Segredo', 'hidden': 1, 'description': '', 'icon': 'https://evil.example/b.jpg', 'icongray': 'https://evil.example/b.jpg'},
    {'name': 'c', 'displayName': 'Lenda', 'hidden': 0, 'description': 'Vire lenda.', 'icon': 'https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/1091500/c.jpg', 'icongray': 'https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/1091500/c_gray.jpg'}]}}}
PLAYER = {'playerstats': {'success': True, 'gameName': 'Cyberpunk 2077', 'achievements': [{'apiname': 'c', 'achieved': 1, 'unlocktime': 1760000000}, {'apiname': 'a', 'achieved': 1, 'unlocktime': 1759000000}, {'apiname': 'b', 'achieved': 0, 'unlocktime': 0}]}}
GLOBAL = {'achievementpercentages': {'achievements': [{'name': 'a', 'percent': 71.3}, {'name': 'b', 'percent': '3.9'}, {'name': 'c', 'percent': 'x'}]}}
RETRO_INFO = {'Title': 'Super Mario World', 'NumDistinctPlayers': 200, 'Achievements': {
    '2': {'ID': 2, 'Title': 'Yoshi', 'Description': 'Encontre o Yoshi.', 'Points': 5, 'BadgeName': '00002', 'DisplayOrder': 2, 'NumAwarded': 150, 'DateEarned': '2026-10-20 21:05:00'},
    '1': {'ID': 1, 'Title': 'Primeiro passo', 'Description': 'Termine a primeira fase.', 'Points': 1, 'BadgeName': '00001', 'DisplayOrder': 1, 'NumAwarded': 190, 'DateEarnedHardcore': '2026-10-20 20:30:00', 'DateEarned': '2026-10-20 20:30:00'},
    '3': {'ID': 3, 'Title': 'Estrela', 'Description': 'Ache a saída secreta.', 'Points': 10, 'BadgeName': 'bad name', 'DisplayOrder': 3, 'NumAwarded': 4}}}


def test_achievement_lists_keep_source_order_hide_foreign_icons_and_expose_rarity():
    fetch = transport({'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements': PLAYER, 'https://api.steampowered.com/ISteamUserStats/GetSchemaForGame': SCHEMA,
                       'https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp': GLOBAL, 'https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php': RETRO_INFO})
    cache = covers.Cache(3600)
    steam = trophies.steam_achievement_list(STEAM, '1091500', fetch, cache)
    assert [item['id'] for item in steam['itens']] == ['a', 'b', 'c'] and steam['obtidos'] == 2 and steam['total'] == 3 and steam['titulo'] == 'Cyberpunk 2077'
    first, hidden, legend = steam['itens']
    assert first['nome'] == 'O Começo' and first['obtida'] and first['obtida_em'] == '2025-09-27T19:06:40+00:00' and first['raridade'] == 71.3 and first['icone'].endswith('/a.jpg')
    assert hidden['oculta'] and not hidden['obtida'] and hidden['icone'] is None and hidden['raridade'] == 3.9, 'foreign icon hosts are dropped; string percentages are read'
    assert legend['raridade'] is None and legend['icone'].startswith('https://steamcdn-a.akamaihd.net/')
    assert set(first) == {'id', 'nome', 'descricao', 'oculta', 'obtida', 'obtida_em', 'icone', 'icone_bloqueado', 'raridade', 'pontos'}
    calls_before = len(fetch.calls)
    trophies.steam_achievement_list(STEAM, '1091500', fetch, cache)
    assert len(fetch.calls) - calls_before == 1, 'schema and rarity come from the cache; only the player state is fetched again'
    retro = trophies.retro_achievement_list(RETRO, '11240', fetch)
    assert [item['nome'] for item in retro['itens']] == ['Primeiro passo', 'Yoshi', 'Estrela'] and retro['obtidos'] == 2 and retro['total'] == 3
    assert retro['itens'][0]['obtida_em'] == '2026-10-20T20:30:00+00:00' and retro['itens'][0]['raridade'] == 95.0 and retro['itens'][0]['pontos'] == 1
    assert retro['itens'][0]['icone'] == 'https://media.retroachievements.org/Badge/00001.png' and retro['itens'][0]['icone_bloqueado'].endswith('00001_lock.png')
    assert retro['itens'][2]['icone'] is None and not retro['itens'][2]['obtida'] and retro['itens'][2]['raridade'] == 2.0
    with pytest.raises(trophies.SourceError):
        trophies.steam_achievement_list(STEAM, '620', transport({}, fail={'https://api.steampowered.com/': 400}))


def test_viewer_route_requires_a_linked_game_and_records_the_counts(tmp_path, monkeypatch):
    fetch = transport({'https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames': RECENT, 'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements': PLAYER,
                       'https://api.steampowered.com/ISteamUserStats/GetSchemaForGame': SCHEMA, 'https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp': GLOBAL})
    monkeypatch.setattr(trophies, 'http_fetch', fetch)
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 5000)) as client:
        _, headers = profile(client)
        manual = client.post('/api/jogos', headers=headers, json={'nome': 'Manual'}).json()
        linked = client.post('/api/jogos', headers=headers, json={'nome': 'Cyberpunk 2077', 'fonte_externa': 'steam', 'id_externo': '1091500', 'trofeus_total': 44, 'trofeus_obtidos': 0}).json()
        assert client.get(f'/api/trofeus/jogo/{manual["id"]}', headers=headers).status_code == 409
        assert client.get(f'/api/trofeus/jogo/{linked["id"]}', headers=headers).status_code == 409, 'nothing linked for this profile yet'
        client.put('/api/trofeus/fontes/steam', headers=headers, json={'api_key': STEAM['api_key'], 'identificacao': STEAM['identificacao']})
        result = client.get(f'/api/trofeus/jogo/{linked["id"]}', headers=headers)
        assert result.status_code == 200, result.text
        body = result.json()
        assert body['jogo']['fonte'] == 'steam' and body['obtidos'] == 2 and body['total'] == 3 and len(body['itens']) == 3 and body['consultado_em']
        game = client.get(f'/api/jogos/{linked["id"]}', headers=headers).json()
        assert game['trofeus_obtidos'] == 2 and game['trofeus_total'] == 3 and game['trofeus_fonte'] == 'steam', 'the viewer refreshes the stored counts'
        assert client.get('/api/trofeus/jogo/999', headers=headers).status_code == 404


def test_bulk_steam_covers_only_for_exact_names_and_never_touch_personal_data(tmp_path, monkeypatch):
    search = {'total': 3, 'items': [{'id': 1091500, 'name': 'Cyberpunk 2077', 'type': 'app'}, {'id': 2138330, 'name': 'Cyberpunk 2077: Phantom Liberty', 'type': 'app'}]}
    ambiguous = {'total': 2, 'items': [{'id': 1, 'name': 'Portal', 'type': 'app'}, {'id': 2, 'name': 'Portal', 'type': 'app'}]}
    nothing = {'total': 1, 'items': [{'id': 3, 'name': 'Outro jogo', 'type': 'app'}]}

    def fetch(url, accept, content_types, max_bytes, allowed_hosts=None, seconds=25, method='GET', body=None, headers=None):
        if url.endswith('.jpg'):
            return 'image/png', image_bytes()
        if 'storesearch' in url:
            value = search if 'yberpunk' in url else ambiguous if 'Portal' in url else nothing
            return 'application/json', json.dumps(value).encode()
        if 'appdetails' in url:
            return 'application/json', json.dumps(APPDETAILS).encode()
        raise AssertionError('URL inesperada: ' + url)
    monkeypatch.setattr(covers, 'fetch', fetch)
    with TestClient(create_app(tmp_path)) as client:
        _, headers = profile(client)
        cyber = client.post('/api/jogos', headers=headers, json={'nome': 'cyberpunk 2077', 'progresso': 40, 'notas': 'minhas', 'genero': 'Ação', 'trofeus_obtidos': 0}).json()
        portal = client.post('/api/jogos', headers=headers, json={'nome': 'Portal'}).json()
        client.post('/api/jogos', headers=headers, json={'nome': 'Inexistente'})
        picture = client.post('/api/imagens?tipo=capa', headers=headers, content=image_bytes()).json()
        client.post('/api/jogos', headers=headers, json={'nome': 'Já com capa', 'capa_id': picture['id']})
        result = client.post('/api/capas/completar', headers=headers)
        assert result.status_code == 200, result.text
        body = result.json()
        assert [g['nome'] for g in body['atualizados']] == ['cyberpunk 2077'] and body['atualizados'][0]['titulo_steam'] == 'Cyberpunk 2077'
        assert {g['nome'] for g in body['sem_correspondencia']} == {'Portal', 'Inexistente'} and body['falhas'] == [] and body['restantes'] is False
        updated = client.get(f'/api/jogos/{cyber["id"]}', headers=headers).json()
        assert updated['capa_id'] and updated['fonte_externa'] == 'steam' and updated['id_externo'] == '1091500' and updated['url_origem'] == 'https://store.steampowered.com/app/1091500/'
        assert updated['progresso'] == 40 and updated['notas'] == 'minhas' and updated['nome'] == 'cyberpunk 2077', 'personal data and the typed name stay'
        assert updated['genero'] == 'Ação' and updated['desenvolvedor'] == 'CD PROJEKT RED' and updated['trofeus_total'] == 3 and updated['trofeus_fonte'] == 'steam', 'only empty fields are filled'
        assert client.get(f'/api/jogos/{portal["id"]}', headers=headers).json()['capa_id'] is None
        again = client.post('/api/capas/completar', headers=headers).json()
        assert again['atualizados'] == [] and len(again['sem_correspondencia']) == 2, 'already linked games are skipped'
