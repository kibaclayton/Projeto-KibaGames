import pytest
from fastapi.testclient import TestClient
from nexus_backend import covers
from nexus_backend.api import create_app


STEAM_RESPONSE = {'total': 4, 'items': [{'id': 1434950, 'name': 'Alan Wake 2', 'tiny_image': 'https://x/capsule.jpg', 'type': 'app'}, {'id': 'não-numérico', 'name': 'Falso'},
                                        {'id': 598190, 'name': 'Alan Wake - Official Soundtrack', 'type': 'app'}, {'id': 108710, 'name': 'Alan Wake', 'type': 'app'}]}
WIKIPEDIA_PT = {'query': {'pages': {
    '2': {'pageid': 2, 'index': 2, 'title': 'Alan Wake (jogo eletrônico)', 'thumbnail': {'source': 'https://upload.wikimedia.org/wikipedia/pt/thumb/a.jpg/400px-a.jpg'}, 'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/a.jpg'}, 'fullurl': 'https://pt.wikipedia.org/wiki/Alan_Wake'},
    '1': {'pageid': 1, 'index': 1, 'title': 'Alan Wake 2', 'thumbnail': {'source': 'https://upload.wikimedia.org/wikipedia/pt/thumb/b.jpg/400px-b.jpg'}, 'original': {'source': 'https://upload.wikimedia.org/wikipedia/pt/b.jpg'}},
    '3': {'pageid': 3, 'index': 3, 'title': 'Sem imagem'},
    '4': {'pageid': 4, 'index': 4, 'title': 'Imagem de outro host', 'original': {'source': 'https://evil.example/capa.jpg'}, 'thumbnail': {'source': 'https://evil.example/capa.jpg'}}}}}


def fake_fetch(responses):
    calls = []

    def fetch_json(url, allowed_hosts):
        calls.append(url)
        for prefix, value in responses.items():
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError('URL inesperada: ' + url)
    fetch_json.calls = calls
    return fetch_json


def profile(client, name='Clayton'):
    created = client.post('/api/perfis', json={'nome': name, 'senha': 'senha-teste-123'})
    session = client.post('/api/sessao', json={'perfil_id': created.json()['id'], 'senha': 'senha-teste-123'})
    return {'Authorization': 'Bearer ' + session.json()['token']}


def test_steam_results_become_portrait_library_art_on_its_own_cdn_only():
    fetch_json = fake_fetch({'https://store.steampowered.com/api/storesearch/': STEAM_RESPONSE})
    items = covers.search_steam('alan wake', fetch_json)
    assert 'term=alan+wake' in fetch_json.calls[0] and 'l=portuguese' in fetch_json.calls[0] and 'cc=BR' in fetch_json.calls[0]
    assert [item['titulo'] for item in items] == ['Alan Wake 2', 'Alan Wake'], 'entries without a numeric app id and soundtracks are dropped'
    assert items[0]['imagem'] == 'https://shared.steamstatic.com/store_item_assets/steam/apps/1434950/library_600x900_2x.jpg'
    assert items[0]['previa'] == items[0]['imagem'], 'the preview reuses the 2x art, which exists for far more games'
    assert items[0]['origem'] == 'https://store.steampowered.com/app/1434950/'
    assert all(item['fonte'] == 'steam' for item in items)


def test_wikipedia_prefers_portuguese_orders_by_rank_and_drops_foreign_image_hosts():
    fetch_json = fake_fetch({'https://pt.wikipedia.org/w/api.php': WIKIPEDIA_PT, 'https://en.wikipedia.org/w/api.php': {'query': {'pages': {}}}})
    items = covers.search_wikipedia('Alan Wake', fetch_json)
    assert len(fetch_json.calls) == 1, 'English is only queried when Portuguese returns nothing'
    assert [item['titulo'] for item in items] == ['Alan Wake 2', 'Alan Wake (jogo eletrônico)'], 'pages without images or on other hosts are dropped'
    assert items[0]['imagem'] == 'https://upload.wikimedia.org/wikipedia/pt/b.jpg'
    assert items[0]['previa'].endswith('400px-b.jpg')
    assert items[1]['origem'] == 'https://pt.wikipedia.org/wiki/Alan_Wake'
    assert items[0]['origem'] == 'https://pt.wikipedia.org/wiki/Alan_Wake_2'
    english = fake_fetch({'https://pt.wikipedia.org/w/api.php': {'query': {'pages': {}}}, 'https://en.wikipedia.org/w/api.php': {'query': {'pages': {'9': {'pageid': 9, 'index': 1, 'title': 'Control (video game)', 'original': {'source': 'https://upload.wikimedia.org/wikipedia/en/c.jpg'}}}}}})
    fallback = covers.search_wikipedia('Control', english)
    assert len(english.calls) == 2 and fallback[0]['titulo'] == 'Control (video game)' and fallback[0]['previa'] == fallback[0]['imagem']


def test_one_source_failing_becomes_a_warning_without_hiding_the_other():
    fetch_json = fake_fetch({'https://store.steampowered.com/api/storesearch/': ValueError('O servidor respondeu HTTP 503.'), 'https://pt.wikipedia.org/w/api.php': WIKIPEDIA_PT})
    result = covers.search_covers('Alan Wake', ('steam', 'wikipedia'), fetch_json)
    assert [item['fonte'] for item in result['itens']] == ['wikipedia', 'wikipedia']
    assert result['avisos'] == ['Steam indisponível no momento (O servidor respondeu HTTP 503.).']
    assert covers.search_covers('Alan Wake', ('inexistente',), fetch_json) == {'itens': [], 'avisos': []}


def test_fetch_json_refuses_hosts_outside_the_source_before_any_connection(monkeypatch):
    monkeypatch.setattr(covers, 'fetch', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('não deveria conectar')))
    from nexus_backend import images
    monkeypatch.setattr(images.socket, 'getaddrinfo', lambda *a, **kw: [(None, None, None, None, ('93.184.216.34', 443))])
    with pytest.raises(ValueError, match='fontes permitidas'):
        images.fetch('https://evil.example/api', 'application/json', ('application/json',), 1024, {'store.steampowered.com'})
    with pytest.raises(ValueError):
        images.fetch('http://store.steampowered.com/api', 'application/json', ('application/json',), 1024, {'store.steampowered.com'})


def test_preview_is_proxied_only_for_source_image_hosts(tmp_path, monkeypatch):
    seen = []

    def fake_fetch(url, accept, content_types, max_bytes, allowed_hosts=None, seconds=25):
        seen.append((url, allowed_hosts, max_bytes))
        if url.endswith('missing.jpg'):
            raise ValueError('O servidor respondeu HTTP 404.')
        return 'image/jpeg', b'\xff\xd8fake'
    monkeypatch.setattr(covers, 'fetch', fake_fetch)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/capas/previa', params={'url': 'https://shared.cloudflare.steamstatic.com/a/library_600x900.jpg'}).status_code == 401
        headers = profile(client)
        good = client.get('/api/capas/previa', params={'url': 'https://shared.cloudflare.steamstatic.com/a/library_600x900.jpg'}, headers=headers)
        assert good.status_code == 200 and good.headers['content-type'].startswith('image/jpeg') and good.content == b'\xff\xd8fake'
        assert seen[0][1] == covers.STEAM_IMAGE_HOSTS | covers.WIKIPEDIA_IMAGE_HOSTS and seen[0][2] == covers.MAX_PREVIEW_BYTES
        assert client.get('/api/capas/previa', params={'url': 'https://evil.example/capa.jpg'}, headers=headers).status_code == 404
        assert client.get('/api/capas/previa', params={'url': 'http://upload.wikimedia.org/capa.jpg'}, headers=headers).status_code == 404
        assert client.get('/api/capas/previa', params={'url': 'https://upload.wikimedia.org/missing.jpg'}, headers=headers).status_code == 404
        assert len(seen) == 2, 'foreign hosts never reach the network layer'


def test_cover_search_endpoint_requires_login_validates_input_and_throttles(tmp_path, monkeypatch):
    monkeypatch.setattr(covers, 'search_steam', lambda name, fetch_json=None: [{'fonte': 'steam', 'titulo': name.upper(), 'imagem': 'https://shared.cloudflare.steamstatic.com/x/library_600x900_2x.jpg', 'previa': 'https://shared.cloudflare.steamstatic.com/x/library_600x900.jpg', 'origem': 'https://store.steampowered.com/app/1/'}])
    monkeypatch.setattr(covers, 'search_wikipedia', lambda name, fetch_json=None: [])
    monkeypatch.setitem(covers.SOURCES, 'steam', covers.search_steam)
    monkeypatch.setitem(covers.SOURCES, 'wikipedia', covers.search_wikipedia)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/capas/busca', params={'nome': 'Alan Wake'}).status_code == 401
        headers = profile(client)
        assert client.get('/api/capas/busca', params={'nome': 'A'}, headers=headers).status_code == 422
        assert client.get('/api/capas/busca', params={'nome': 'Alan Wake', 'fonte': 'google'}, headers=headers).status_code == 422
        result = client.get('/api/capas/busca', params={'nome': '  Alan Wake  '}, headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()['itens'][0]['titulo'] == 'ALAN WAKE' and result.json()['avisos'] == []
        assert client.get('/api/capas/busca', params={'nome': 'Alan Wake', 'fonte': 'wikipedia'}, headers=headers).json()['itens'] == []
        for _ in range(18):
            assert client.get('/api/capas/busca', params={'nome': 'Alan Wake'}, headers=headers).status_code == 200
        assert client.get('/api/capas/busca', params={'nome': 'Alan Wake'}, headers=headers).status_code == 429
