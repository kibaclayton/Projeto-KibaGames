"""Detalhes por identificador, aplicação de um resultado, duplicatas, cache e migração da ficha do jogo."""
import sqlite3
import pytest
from fastapi.testclient import TestClient
from nexus_backend import covers
from nexus_backend.api import create_app
from nexus_backend.database import MIGRATIONS, SCHEMA, SCHEMA_VERSION, Database
from tests.test_api import image_bytes
from tests.test_covers import fake_fetch, profile

STEAM_DETAILS = {'367520': {'success': True, 'data': {
    'type': 'game', 'name': 'Hollow Knight', 'steam_appid': 367520, 'short_description': 'Forge your own path in <b>Hollow Knight</b>! &amp; more',
    'developers': ['Team Cherry'], 'publishers': ['Team Cherry'], 'platforms': {'windows': True, 'mac': True, 'linux': True},
    'genres': [{'id': '1', 'description': 'Ação'}, {'id': '25', 'description': 'Aventura'}, {'id': '23', 'description': 'Indie'}],
    'release_date': {'coming_soon': False, 'date': '24 fev. 2017'}, 'price_overview': {'final': 4699}, 'website': 'https://example.test'}}}
WIKIDATA_GAME = {'entities': {'Q126199700': {'type': 'item', 'id': 'Q126199700', 'labels': {'pt': {'language': 'pt', 'value': 'Astro Bot'}}, 'claims': {
    'P31': [{'mainsnak': {'datavalue': {'value': {'id': 'Q7889'}}}}],
    'P400': [{'mainsnak': {'datavalue': {'value': {'id': 'Q63184502'}}}}],
    'P136': [{'mainsnak': {'datavalue': {'value': {'id': 'Q828322'}}}}],
    'P577': [{'mainsnak': {'datavalue': {'value': {'time': '+2024-09-06T00:00:00Z', 'precision': 11}}}},
             {'mainsnak': {'datavalue': {'value': {'time': '+2025-01-01T00:00:00Z', 'precision': 9}}}}],
    'P178': [{'mainsnak': {'datavalue': {'value': {'id': 'Q107198400'}}}}],
    'P123': [{'mainsnak': {'datavalue': {'value': {'id': 'Q18594'}}}}]},
    'sitelinks': {'ptwiki': {'site': 'ptwiki', 'title': 'Astro Bot', 'url': 'https://pt.wikipedia.org/wiki/Astro_Bot'}}}}}
WIKIDATA_LABELS = {'entities': {'Q828322': {'labels': {'pt-br': {'language': 'pt-br', 'value': 'jogo eletrônico de plataforma'}}},
                                'Q107198400': {'labels': {'en': {'language': 'en', 'value': 'Team Asobi'}}},
                                'Q18594': {'labels': {'pt': {'language': 'pt', 'value': 'Sony Interactive Entertainment'}}}}}
WIKIPEDIA_SUMMARY = {'query': {'pages': {'1': {'pageid': 1, 'title': 'Astro Bot', 'extract': 'Astro Bot é um jogo de plataforma de 2024.',
                                               'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/5/58/Astro_Bot_capa.png'},
                                               'thumbnail': {'source': 'https://upload.wikimedia.org/wikipedia/pt/thumb/5/58/Astro_Bot_capa.png/400px-Astro_Bot_capa.png'}}}}}
WIKIPEDIA_SEARCH = {'query': {'pages': {
    '1': {'pageid': 1, 'index': 1, 'title': 'Astro Bot', 'pageprops': {'wikibase_item': 'Q126199700'}, 'fullurl': 'https://pt.wikipedia.org/wiki/Astro_Bot',
          'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/5/58/Astro_Bot_capa.png'}, 'thumbnail': {'source': 'https://upload.wikimedia.org/wikipedia/pt/thumb/a.png/400px-a.png'}},
    '2': {'pageid': 2, 'index': 2, 'title': 'The Game Awards 2024', 'pageprops': {'wikibase_item': 'Q130000001'}, 'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/b.png'}},
    '3': {'pageid': 3, 'index': 3, 'title': 'Artigo sem item', 'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/c.png'}}}}}
WIKIDATA_BATCH = {'entities': {'Q126199700': {'claims': WIKIDATA_GAME['entities']['Q126199700']['claims']},
                               'Q130000001': {'claims': {'P31': [{'mainsnak': {'datavalue': {'value': {'id': 'Q1300000'}}}}]}}}}


def steam_fetch():
    return fake_fetch({'https://store.steampowered.com/api/appdetails': STEAM_DETAILS})


def test_steam_details_are_typed_normalized_and_never_echo_the_raw_payload():
    fetch_json = steam_fetch()
    details = covers.steam_details('367520', fetch_json)
    assert 'appids=367520' in fetch_json.calls[0] and 'l=portuguese' in fetch_json.calls[0]
    assert details['titulo'] == 'Hollow Knight' and details['id'] == '367520' and details['fonte'] == 'steam'
    assert details['data_lancamento'] == '2017-02-24' and details['ano'] == 2017
    assert details['plataformas'] == ['Windows', 'macOS', 'Linux'] and details['plataformas_nexus'] == ['PC']
    assert details['generos'] == ['Ação', 'Aventura', 'Indie'] and details['genero'] == 'Ação'
    assert details['desenvolvedores'] == ['Team Cherry'] and details['publicadoras'] == ['Team Cherry']
    assert details['descricao'] == 'Forge your own path in Hollow Knight! & more', 'HTML tags and entities are stripped'
    assert details['imagem'] == 'https://shared.steamstatic.com/store_item_assets/steam/apps/367520/library_600x900_2x.jpg'
    assert 'price_overview' not in details and 'website' not in details and set(details) == set(covers._details('steam', '1', 't', None, 'o'))


def test_steam_dates_in_portuguese_english_or_year_only_and_missing_games():
    assert covers.parse_steam_date('24 fev. 2017') == ('2017-02-24', 2017)
    assert covers.parse_steam_date('24 Feb, 2017') == ('2017-02-24', 2017)
    assert covers.parse_steam_date('Feb 24, 2017') == ('2017-02-24', 2017)
    assert covers.parse_steam_date('1 out. 2026') == ('2026-10-01', 2026)
    assert covers.parse_steam_date('2026') == (None, 2026) and covers.parse_steam_date('Q4 2026') == (None, 2026)
    assert covers.parse_steam_date('Em breve') == (None, None) and covers.parse_steam_date('') == (None, None)
    missing = fake_fetch({'https://store.steampowered.com/api/appdetails': {'999': {'success': False}}})
    with pytest.raises(ValueError, match='não encontrado'):
        covers.steam_details('999', missing)
    with pytest.raises(ValueError, match='inválido'):
        covers.steam_details('abc', missing)
    coming = fake_fetch({'https://store.steampowered.com/api/appdetails': {'5': {'success': True, 'data': {'name': 'Futuro', 'release_date': {'coming_soon': True, 'date': '2027'}}}}})
    soon = covers.steam_details('5', coming)
    assert soon['data_lancamento'] is None and soon['ano'] is None and soon['plataformas'] == [] and soon['genero'] == ''


def test_wikidata_details_resolve_labels_release_date_and_wikipedia_summary():
    fetch_json = fake_fetch({'https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids=Q126199700': WIKIDATA_GAME,
                             'https://www.wikidata.org/w/api.php?action=wbgetentities&format=json&ids=Q107198400': WIKIDATA_LABELS,
                             'https://pt.wikipedia.org/w/api.php': WIKIPEDIA_SUMMARY})
    details = covers.wikipedia_details('Q126199700', fetch_json)
    assert len(fetch_json.calls) == 3, 'entity, labels of referenced items (platform label comes from the built-in table), article summary'
    assert details['titulo'] == 'Astro Bot' and details['origem'] == 'https://pt.wikipedia.org/wiki/Astro_Bot'
    assert details['data_lancamento'] == '2024-09-06' and details['ano'] == 2024, 'the earliest full-precision date wins over a year-only one'
    assert details['plataformas'] == ['PlayStation 5'] and details['plataformas_nexus'] == ['PS5']
    assert details['generos'] == ['jogo eletrônico de plataforma'] and details['genero'] == 'Plataforma'
    assert details['desenvolvedores'] == ['Team Asobi'] and details['publicadoras'] == ['Sony Interactive Entertainment']
    assert details['descricao'] == 'Astro Bot é um jogo de plataforma de 2024.' and details['imagem'].endswith('Astro_Bot_capa.png')
    with pytest.raises(ValueError):
        covers.wikipedia_details('Q1', fake_fetch({'https://www.wikidata.org/w/api.php': {'entities': {'Q1': {'missing': ''}}}}))
    with pytest.raises(ValueError, match='inválido'):
        covers.wikipedia_details('../etc', fetch_json)


def test_wikipedia_search_carries_wikidata_ids_year_platforms_and_drops_non_games():
    fetch_json = fake_fetch({'https://pt.wikipedia.org/w/api.php': WIKIPEDIA_SEARCH, 'https://www.wikidata.org/w/api.php': WIKIDATA_BATCH})
    items = covers.search_wikipedia('Astro Bot', fetch_json)
    assert len(fetch_json.calls) == 2 and 'ppprop=wikibase_item' in fetch_json.calls[0] and 'ids=Q126199700%7CQ130000001' in fetch_json.calls[1]
    assert [(item['id'], item['titulo']) for item in items] == [('Q126199700', 'Astro Bot'), ('pt:3', 'Artigo sem item')], 'awards ceremony dropped; page without item kept'
    assert items[0]['ano'] == 2024 and items[0]['plataformas'] == ['PlayStation 5'] and items[1]['ano'] is None
    offline = fake_fetch({'https://pt.wikipedia.org/w/api.php': WIKIPEDIA_SEARCH, 'https://www.wikidata.org/w/api.php': OSError('timeout')})
    cache = covers.Cache(seconds=100)
    degraded = covers.search_covers('Astro Bot', ('wikipedia',), offline, cache)
    assert [item['id'] for item in degraded['itens']] == ['Q126199700', 'Q130000001', 'pt:3'], 'without Wikidata nothing is filtered, but the search still works'
    assert degraded['avisos'] and 'Wikidata' in degraded['avisos'][0] and cache.items == {}, 'a partial answer is announced and never cached'


def test_origins_titles_and_ids_from_providers_are_sanitised():
    hostile = {'query': {'pages': {'1': {'pageid': 1, 'index': 1, 'title': '<b>Jogo</b>  Estranho', 'fullurl': 'https://evil.example/phish',
                                        'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/x.png'}},
                                  '2': {'pageid': 'não-numérico', 'index': 2, 'title': 'Sem id', 'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/y.png'}}}}}
    items = covers.search_wikipedia('Jogo', fake_fetch({'https://pt.wikipedia.org/w/api.php': hostile}))
    assert [item['titulo'] for item in items] == ['Jogo Estranho'], 'tags stripped, pages without a numeric id dropped'
    assert items[0]['origem'] == 'https://pt.wikipedia.org/wiki/Jogo_Estranho', 'a foreign fullurl is replaced by the article address'
    assert covers._origin_allowed('https://store.steampowered.com/app/1/') and covers._origin_allowed('https://www.wikidata.org/wiki/Q1')
    assert not covers._origin_allowed('https://user@pt.wikipedia.org/wiki/X') and not covers._origin_allowed('https://pt.wikipedia.org:8443/wiki/X') and not covers._origin_allowed('javascript:alert(1)')
    steam = covers.search_steam('x', fake_fetch({'https://store.steampowered.com/api/storesearch/': {'items': [{'id': True, 'name': 'Bool'}, {'id': -5, 'name': 'Negativo'}, {'id': 10 ** 11, 'name': 'Enorme'}, {'id': 7, 'name': ' <i>Ok</i> '}]}}))
    assert [(item['id'], item['titulo']) for item in steam] == [('7', 'Ok')]
    import time
    started = time.monotonic()
    assert covers._text('<' * 400000 + 'fim', 2000) == '<' * 2000, 'hostile markup is cut before the regex and never costs quadratic time'
    assert time.monotonic() - started < 2
    assert covers._text('<p>Olá,&nbsp;mundo !</p>', 100) == 'Olá, mundo!'
    with pytest.raises(ValueError):
        covers.steam_details('٣٦٧٥٢٠', steam_fetch())  # dígitos não ASCII não contam como appid


def test_search_survives_http_client_errors_and_games_need_source_and_id_together(tmp_path, monkeypatch):
    import http.client
    broken = fake_fetch({'https://store.steampowered.com/api/storesearch/': http.client.IncompleteRead(b'')})
    result = covers.search_covers('x', ('steam',), broken)
    assert result['itens'] == [] and 'Steam indisponível' in result['avisos'][0]
    with TestClient(create_app(tmp_path)) as client:
        headers = profile(client)
        assert client.post('/api/jogos', headers=headers, json={'nome': 'X', 'fonte_externa': 'steam'}).status_code == 422
        assert client.post('/api/jogos', headers=headers, json={'nome': 'X', 'id_externo': '1'}).status_code == 422
        assert client.post('/api/jogos', headers=headers, json={'nome': 'X', 'url_origem': 'https://user:pw@store.steampowered.com/app/1/'}).status_code == 422
        assert client.post('/api/jogos', headers=headers, json={'nome': 'X', 'url_origem': 'https://store.steampowered.com:8443/app/1/'}).status_code == 422
        ok = client.post('/api/jogos', headers=headers, json={'nome': 'X', 'fonte_externa': 'wikipedia', 'id_externo': 'Q1', 'url_origem': 'https://pt.wikipedia.org/wiki/X'})
        assert ok.status_code == 201, ok.text


def test_cache_separates_sources_and_queries_and_expires(monkeypatch):
    cache = covers.Cache(seconds=100)
    calls = []

    def search(name, fetch_json=None):
        calls.append(name)
        return [{'fonte': 'steam', 'id': '1', 'titulo': name, 'imagem': 'https://shared.steamstatic.com/x/library_600x900_2x.jpg', 'previa': 'https://shared.steamstatic.com/x/library_600x900_2x.jpg', 'origem': 'https://store.steampowered.com/app/1/', 'ano': None, 'plataformas': []}]
    monkeypatch.setitem(covers.SOURCES, 'steam', search)
    first = covers.search_covers('Hollow  Knight', ('steam',), cache=cache)
    assert covers.search_covers('hollow knight', ('steam',), cache=cache) == first and calls == ['Hollow  Knight'], 'case and spacing share one entry'
    covers.search_covers('Hollow Knight', ('wikipedia', 'steam'), cache=cache)
    covers.search_covers('Silksong', ('steam',), cache=cache)
    assert calls == ['Hollow  Knight', 'Hollow Knight', 'Silksong'], 'different source sets and queries are separate entries'
    first['itens'][0]['titulo'] = 'alterado'
    assert covers.search_covers('hollow knight', ('steam',), cache=cache)['itens'][0]['titulo'] == 'Hollow  Knight', 'cached values are copies'
    now = [1000.0]
    monkeypatch.setattr(covers.time, 'monotonic', lambda: now[0])
    cache.set('k', {'a': 1})
    now[0] += 101
    assert cache.get('k') is None
    failing = fake_fetch({'https://store.steampowered.com/api/storesearch/': ValueError('HTTP 503')})
    monkeypatch.setitem(covers.SOURCES, 'steam', covers.search_steam)
    assert covers.search_covers('x', ('steam',), failing, cache)['avisos'] and cache.get(covers.json.dumps(['busca', ['steam'], 'x'])) is None, 'warnings are not cached'


def test_apply_endpoint_uses_the_server_side_identity_only_and_reports_duplicates(tmp_path, monkeypatch):
    downloads = []

    def fake_fetch_bytes(url, accept, content_types, max_bytes, allowed_hosts=None, seconds=25):
        downloads.append((url, allowed_hosts))
        return 'image/png', image_bytes()
    monkeypatch.setattr(covers, 'fetch', fake_fetch_bytes)
    steam = steam_fetch()
    monkeypatch.setitem(covers.DETAILS, 'steam', lambda external_id, fetch_json=None: covers.steam_details(external_id, steam))
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/capas/aplicar', json={'fonte': 'steam', 'id': '367520'}).status_code == 401
        headers = profile(client)
        assert client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'steam', 'id': '367520', 'imagem': 'https://evil.example/x.jpg'}).status_code == 422, 'extra fields such as a URL are refused'
        assert client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'google', 'id': '1'}).status_code == 422
        assert client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'steam', 'id': '../x'}).status_code == 422
        result = client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'steam', 'id': '367520'})
        assert result.status_code == 201, result.text
        body = result.json()
        assert body['detalhes']['titulo'] == 'Hollow Knight' and body['detalhes']['genero'] == 'Ação' and body['erro_capa'] == '' and body['duplicado_em'] is None
        assert body['imagem']['tipo'] == 'capa' and body['imagem']['largura'] == 600
        assert downloads == [('https://shared.steamstatic.com/store_item_assets/steam/apps/367520/library_600x900_2x.jpg', covers.STEAM_IMAGE_HOSTS)], 'the cover URL is rebuilt from the id'
        game = client.post('/api/jogos', headers=headers, json={'nome': 'Hollow Knight', 'capa_id': body['imagem']['id'], 'fonte_externa': 'steam', 'id_externo': '367520',
                                                                 'data_lancamento': '2017-02-24', 'desenvolvedor': 'Team Cherry', 'url_origem': 'https://store.steampowered.com/app/367520/'})
        assert game.status_code == 201, game.text
        assert game.json()['fonte_externa'] == 'steam' and game.json()['data_lancamento'] == '2017-02-24' and game.json()['data_inicio'] is None, 'release date never lands in the personal start date'
        again = client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'steam', 'id': '367520'}).json()
        assert again['duplicado_em'] == {'id': game.json()['id'], 'nome': 'Hollow Knight', 'plataforma': 'PC'}
        same_game = client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'steam', 'id': '367520', 'jogo_id': game.json()['id']}).json()
        assert same_game['duplicado_em'] is None, 'editing the game that owns the id is not a duplicate'
        other = client.get('/api/capas/detalhes', headers=headers, params={'fonte': 'steam', 'id': '367520'})
        assert other.status_code == 200 and other.json()['duplicado_em']['id'] == game.json()['id']
        assert len(steam.calls) == 1, 'details are served from the cache after the first provider call'
        stranger = profile(client, 'Outra')
        assert client.post('/api/capas/aplicar', headers=stranger, json={'fonte': 'steam', 'id': '367520'}).json()['duplicado_em'] is None, 'duplicates are per profile'
        listed = client.get('/api/jogos', headers=headers).json()['itens'][0]
        assert listed['fonte_externa'] == 'steam' and listed['id_externo'] == '367520' and listed['desenvolvedor'] == 'Team Cherry' and 'descricao' not in listed
        bad = client.post('/api/jogos', headers=headers, json={'nome': 'X', 'url_origem': 'http://insecure.example/'})
        assert bad.status_code == 422


def test_apply_without_a_cover_still_returns_the_details(tmp_path, monkeypatch):
    monkeypatch.setitem(covers.DETAILS, 'wikipedia', lambda external_id, fetch_json=None: covers._details('wikipedia', external_id, 'Sem capa', None, 'https://pt.wikipedia.org/wiki/X', generos=['RPG']))
    with TestClient(create_app(tmp_path)) as client:
        headers = profile(client)
        body = client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'wikipedia', 'id': 'pt:9'}).json()
        assert body['imagem'] is None and 'não tem capa' in body['erro_capa'] and body['detalhes']['genero'] == 'RPG'

    def failing(external_id, fetch_json=None):
        raise ValueError('O servidor respondeu HTTP 503.')
    monkeypatch.setitem(covers.DETAILS, 'wikipedia', failing)
    with TestClient(create_app(tmp_path / 'b')) as client:
        headers = profile(client)
        failed = client.post('/api/capas/aplicar', headers=headers, json={'fonte': 'wikipedia', 'id': 'Q1'})
        assert failed.status_code == 404 and 'HTTP 503' in failed.json()['detail']


def test_migration_to_schema_4_keeps_every_game_and_adds_optional_fields(tmp_path):
    db = Database(tmp_path)
    conn = sqlite3.connect(db.path)
    conn.executescript('BEGIN;\n' + SCHEMA + '\nCOMMIT;')
    for target in (2, 3):
        conn.executescript('BEGIN;\n' + MIGRATIONS[target] + '\nCOMMIT;')
    conn.execute("INSERT INTO usuarios(id,nome,nome_chave,senha_hash) VALUES(1,'Clayton','clayton','x')")
    conn.execute("INSERT INTO jogos(usuario_id,nome,nome_chave,plataforma,progresso,data_inicio,notas,cronograma,genero) VALUES(1,'Alan Wake 2','alan wake 2','PS5',65,'2026-09-07','minhas notas','{\"2026-09-07\": \"single\"}','Terror')")
    conn.execute("INSERT INTO jogos(usuario_id,nome,nome_chave,plataforma) VALUES(1,'Control','control','PC')")
    conn.commit()
    assert conn.execute('PRAGMA user_version').fetchone()[0] == 3
    conn.close()
    db.initialize()
    with db.connection() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION == 7
        rows = [dict(row) for row in conn.execute('SELECT * FROM jogos ORDER BY id')]
    assert [row['nome'] for row in rows] == ['Alan Wake 2', 'Control']
    assert rows[0]['progresso'] == 65 and rows[0]['data_inicio'] == '2026-09-07' and rows[0]['notas'] == 'minhas notas' and rows[0]['genero'] == 'Terror'
    assert rows[0]['data_lancamento'] is None and rows[0]['desenvolvedor'] == '' and rows[0]['fonte_externa'] == '' and rows[0]['url_origem'] == ''
    with TestClient(create_app(tmp_path)) as client:
        session = client.post('/api/sessao', json={'perfil_id': 1, 'senha': 'qualquer'})
        assert session.status_code == 401, 'the synthetic hash is not a real password; the app still opens the migrated database'
        assert client.get('/api/saude').json()["schema"] == 7
