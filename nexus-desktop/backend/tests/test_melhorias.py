"""Melhorias de 25/10/2026: ordem manual, preferências, galeria de avatares, filtro de plataforma, IGDB opcional e troféus."""
import json
import sqlite3
from fastapi.testclient import TestClient
from nexus_backend import avatars, covers, igdb
from nexus_backend.api import create_app
from nexus_backend.database import MIGRATIONS, SCHEMA, SCHEMA_VERSION, Database
from tests.test_api import image_bytes, profile
from tests.test_covers import fake_fetch


def games_of(client, headers, **params):
    return [g['nome'] for g in client.get('/api/jogos', headers=headers, params=params).json()['itens']]


def test_manual_order_is_per_profile_atomic_and_independent_from_collection_order(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        _, mine = profile(client)
        _, other = profile(client, 'Outra')
        ids = [client.post('/api/jogos', headers=mine, json={'nome': name}).json()['id'] for name in ('Zelda', 'Alan Wake', 'Metro')]
        client.post('/api/jogos', headers=other, json={'nome': 'Jogo alheio'})
        assert games_of(client, mine) == ['Zelda', 'Alan Wake', 'Metro'], 'new games land at the end of the manual order'
        assert games_of(client, mine, ordenacao='nome') == ['Alan Wake', 'Metro', 'Zelda']
        assert client.put('/api/jogos/ordem', headers=mine, json={'ids': [ids[2], ids[0]]}).json()['total'] == 3
        assert games_of(client, mine) == ['Metro', 'Zelda', 'Alan Wake'], 'listed ids come first; the rest keep their relative order'
        assert client.put('/api/jogos/ordem', headers=mine, json={'ids': [ids[0], 999]}).status_code == 404
        assert client.put('/api/jogos/ordem', headers=mine, json={'ids': [ids[0], ids[0]]}).status_code == 422
        assert games_of(client, mine) == ['Metro', 'Zelda', 'Alan Wake'], 'a failed update changes nothing'
        assert client.put('/api/jogos/ordem', headers=other, json={'ids': [ids[0]]}).status_code == 404, 'another profile cannot touch my games'
        collection = client.post('/api/colecoes', headers=mine, json={'nome': 'Série'}).json()['id']
        client.patch(f'/api/jogos/{ids[1]}', headers=mine, json={'colecao_id': collection, 'ordem': 1})
        client.patch(f'/api/jogos/{ids[0]}', headers=mine, json={'colecao_id': collection, 'ordem': 2})
        assert games_of(client, mine, colecao_id=collection, ordenacao='colecao') == ['Alan Wake', 'Zelda'], 'collection order stays its own field'
        assert games_of(client, mine) == ['Metro', 'Zelda', 'Alan Wake']


def test_still_playing_clears_the_end_date_and_keeps_progress(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        _, headers = profile(client)
        game = client.post('/api/jogos', headers=headers, json={'nome': 'Hades', 'progresso': 100, 'data_inicio': '2026-09-01', 'data_termino': '2026-09-20', 'ainda_jogando': True}).json()
        assert game['ainda_jogando'] is True and game['data_termino'] is None and game['progresso'] == 100
        done = client.patch(f'/api/jogos/{game["id"]}', headers=headers, json={'ainda_jogando': False, 'data_termino': '2026-09-25'}).json()
        assert done['ainda_jogando'] is False and done['data_termino'] == '2026-09-25'


def test_preferences_are_validated_and_per_profile(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        _, mine = profile(client)
        _, other = profile(client, 'Outra')
        assert client.get('/api/conta/preferencias', headers=mine).json() == {'tema': 'escuro', 'movimento': 'padrao', 'densidade': 'confortavel', 'destaque': 'roxo'}
        saved = client.put('/api/conta/preferencias', headers=mine, json={'tema': 'claro', 'movimento': 'reduzida', 'densidade': 'compacta', 'destaque': 'verde'})
        assert saved.status_code == 200 and client.get('/api/conta/preferencias', headers=mine).json()['destaque'] == 'verde'
        assert client.get('/api/conta/preferencias', headers=other).json()['tema'] == 'escuro', 'the other profile keeps its own defaults'
        assert client.put('/api/conta/preferencias', headers=mine, json={'tema': 'claro', 'destaque': '#ff0000'}).status_code == 422, 'no arbitrary colours'
        assert client.put('/api/conta/preferencias', headers=mine, json={'tema': 'claro', 'css': 'body{}'}).status_code == 422


def test_avatar_gallery_holds_five_photos_switches_the_active_one_and_stays_private(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        _, mine = profile(client)
        _, other = profile(client, 'Outra')
        images = [client.post('/api/imagens?tipo=avatar', headers=mine, content=image_bytes((200 + i, 200 + i))).json()['id'] for i in range(6)]
        for i in range(5):
            assert client.put('/api/conta/avatar', headers=mine, json={'imagem_id': images[i]}).status_code == 200
        gallery = client.get('/api/conta/avatares', headers=mine).json()
        assert [slot['imagem_id'] for slot in gallery] == images[:5] and [slot['ativo'] for slot in gallery] == [False, False, False, False, True]
        assert client.put('/api/conta/avatar', headers=mine, json={'imagem_id': images[5]}).status_code == 409, 'a sixth photo requires choosing a slot to replace'
        replaced = client.put('/api/conta/avatares/5', headers=mine, json={'imagem_id': images[5]}).json()
        assert replaced[4]['imagem_id'] == images[5] and replaced[4]['ativo'], 'replacing the active slot keeps the slot active with the new photo'
        assert client.get('/api/perfis').json()[0]['avatar_id'] == images[5]
        assert client.put('/api/conta/avatar', headers=mine, json={'imagem_id': images[0]}).status_code == 200, 'switching among gallery photos needs no upload'
        removed = client.delete('/api/conta/avatares/1', headers=mine).json()
        assert removed[0]['imagem_id'] is None
        assert client.get('/api/perfis').json()[0]['avatar_id'] == images[1], 'removing the active photo activates the next one'
        assert client.delete('/api/conta/avatares/1', headers=mine).status_code == 404
        assert client.put('/api/conta/avatares/9', headers=mine, json={'imagem_id': images[0]}).status_code == 422
        assert client.put('/api/conta/avatares/2', headers=other, json={'imagem_id': images[0]}).status_code == 404, 'another profile cannot use my images'
        assert client.get('/api/conta/avatares', headers=other).json()[0]['imagem_id'] is None
        assert client.get(f'/api/imagens/{images[2]}', headers=other).status_code == 404, 'non-active photos stay private'


def test_commons_search_keeps_only_bitmap_images_from_wikimedia_with_license():
    fixture = {'query': {'pages': {
        '1': {'pageid': 1, 'index': 2, 'title': 'File:Wolf.jpg', 'fullurl': 'https://commons.wikimedia.org/wiki/File:Wolf.jpg', 'imageinfo': [{'url': 'https://upload.wikimedia.org/wikipedia/commons/w/wolf.jpg', 'thumburl': 'https://upload.wikimedia.org/wikipedia/commons/thumb/w/wolf.jpg/1024px-wolf.jpg', 'mime': 'image/jpeg',
              'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'}, 'Artist': {'value': '<a href="x">Ana</a>'}}}]},
        '2': {'pageid': 2, 'index': 1, 'title': 'File:Logo.svg', 'imageinfo': [{'url': 'https://upload.wikimedia.org/a.svg', 'thumburl': 'https://upload.wikimedia.org/a.png', 'mime': 'image/svg+xml'}]},
        '3': {'pageid': 3, 'index': 3, 'title': 'File:Evil.png', 'imageinfo': [{'url': 'https://evil.example/a.png', 'thumburl': 'https://evil.example/a.png', 'mime': 'image/png'}]}}}}
    items = avatars.search_commons('wolf', fake_fetch({'https://commons.wikimedia.org/w/api.php': fixture}))
    assert [item['titulo'] for item in items] == ['Wolf.jpg'] and items[0]['licenca'] == 'CC BY-SA 4.0' and items[0]['autor'] == 'Ana'
    assert items[0]['previa'].startswith('https://upload.wikimedia.org/') and items[0]['origem'] == 'https://commons.wikimedia.org/wiki/File:Wolf.jpg'


def test_platform_family_filter_and_steam_trophy_total():
    steam = {'items': [{'id': 7, 'name': 'Hades', 'platforms': {'windows': True}}]}
    pt = {'query': {'pages': {'1': {'pageid': 1, 'index': 1, 'title': 'Astro Bot', 'pageprops': {'wikibase_item': 'Q1'}, 'original': {'source': 'https://upload.wikimedia.org/a.png'}},
                              '2': {'pageid': 2, 'index': 2, 'title': 'Hades', 'pageprops': {'wikibase_item': 'Q2'}, 'original': {'source': 'https://upload.wikimedia.org/b.png'}}}}}
    wikidata = {'entities': {'Q1': {'claims': {'P400': [{'mainsnak': {'datavalue': {'value': {'id': 'Q63184502'}}}}]}},
                             'Q2': {'claims': {'P400': [{'mainsnak': {'datavalue': {'value': {'id': 'Q1406'}}}}, {'mainsnak': {'datavalue': {'value': {'id': 'Q19610114'}}}}]}}}}
    fetch_json = fake_fetch({'https://store.steampowered.com/api/storesearch/': steam, 'https://pt.wikipedia.org/w/api.php': pt, 'https://www.wikidata.org/w/api.php': wikidata})
    everything = covers.search_covers('x', ('steam', 'wikipedia', 'igdb'), fetch_json, family='todas')
    assert [(i['fonte'], i['titulo']) for i in everything['itens']] == [('steam', 'Hades'), ('wikipedia', 'Astro Bot'), ('wikipedia', 'Hades')] and everything['avisos'] == []
    playstation = covers.search_covers('x', ('steam', 'wikipedia', 'igdb'), fetch_json, family='playstation')
    assert [i['titulo'] for i in playstation['itens']] == ['Astro Bot'], 'Steam is skipped for consoles; Wikidata platforms decide'
    assert playstation['avisos'] == [covers.IGDB_HINT], 'console searches explain that IGDB is not configured'
    nintendo = covers.search_covers('x', ('steam', 'wikipedia'), fetch_json, family='nintendo')
    assert [i['titulo'] for i in nintendo['itens']] == ['Hades']
    assert covers.matches_family(['Xbox Series X e Series S'], 'xbox') and not covers.matches_family([], 'xbox') and covers.matches_family([], 'todas')
    details = covers.steam_details('7', fake_fetch({'https://store.steampowered.com/api/appdetails': {'7': {'success': True, 'data': {'name': 'Hades', 'achievements': {'total': 49}}}}}))
    assert details['trofeus_total'] == 49 and details['trofeus_fonte'] == 'steam' and details['trofeus_escopo'] == 'jogo base' and details['trofeus_consultado_em']
    none = covers.steam_details('7', fake_fetch({'https://store.steampowered.com/api/appdetails': {'7': {'success': True, 'data': {'name': 'Sem', 'achievements': {'total': 0}}}}}))
    assert none['trofeus_total'] is None and none['trofeus_fonte'] == '' and none['trofeus_consultado_em'] is None, 'zero is not a total: it stays "não informado"'


def test_igdb_provider_uses_the_local_key_and_never_leaks_it(tmp_path):
    calls = []

    def fake(url, accept, content_types, max_bytes, allowed_hosts=None, seconds=25, method='GET', body=None, headers=None):
        calls.append((url, method, body, headers))
        if 'id.twitch.tv' in url:
            return 'application/json', json.dumps({'access_token': 'tok', 'expires_in': 3600}).encode()
        if body and body.startswith(b'search'):
            return 'application/json', json.dumps([{'id': 1942, 'name': 'The Witcher 3: Wild Hunt', 'version_title': 'Complete Edition', 'cover': {'image_id': 'co1wyy'}, 'platforms': [{'name': 'PlayStation 5'}, {'name': 'Nintendo Switch'}], 'first_release_date': 1431993600, 'url': 'https://www.igdb.com/games/the-witcher-3'}, {'id': 2, 'name': 'Sem capa'}]).encode()
        return 'application/json', json.dumps([{'id': 1942, 'name': 'The Witcher 3: Wild Hunt', 'summary': 'RPG.', 'genres': [{'name': 'Role-playing (RPG)'}], 'platforms': [{'name': 'PlayStation 5'}], 'first_release_date': 1431993600,
                                                'involved_companies': [{'developer': True, 'publisher': True, 'company': {'name': 'CD Projekt Red'}}], 'cover': {'image_id': 'co1wyy'}}]).encode()
    config = {'client_id': 'abcdefghij1234', 'client_secret': 'secretsecret12'}
    items = igdb.search(config, 'witcher', 'playstation', fake)
    assert [i['titulo'] for i in items] == ['The Witcher 3: Wild Hunt (Complete Edition)'] and items[0]['ano'] == 2015 and items[0]['plataformas'] == ['PlayStation 5', 'Nintendo Switch']
    assert items[0]['imagem'] == 'https://images.igdb.com/igdb/image/upload/t_cover_big/co1wyy.jpg' and items[0]['id'] == '1942'
    assert b'where platforms = (7,8,9,48,167,38,46)' in calls[1][2] and calls[1][3]['Client-ID'] == config['client_id']
    assert 'secretsecret12' not in json.dumps(items), 'the secret never reaches the results'
    raw = igdb.details(config, '1942', fake)
    assert raw['desenvolvedores'] == ['CD Projekt Red'] and raw['data_lancamento'] == '2015-05-19' and raw['plataformas'] == ['PlayStation 5']
    assert len([c for c in calls if 'id.twitch.tv' in c[0]]) == 1, 'the token is cached between calls'
    assert igdb.load_config(tmp_path) is None
    (tmp_path / 'igdb.json').write_text(json.dumps(config), encoding='utf-8')
    assert igdb.configured(tmp_path) and igdb.load_config(tmp_path) == config
    (tmp_path / 'igdb.json').write_text('{"client_id": "x y", "client_secret": "z"}', encoding='utf-8')
    assert igdb.load_config(tmp_path) is None, 'malformed credentials are ignored'
    with TestClient(create_app(tmp_path)) as client:
        _, headers = profile(client)
        assert client.get('/api/capas/fontes', headers=headers).json()['igdb_configurada'] is False


def test_migration_to_schema_5_keeps_games_and_seeds_positions_and_gallery(tmp_path):
    db = Database(tmp_path)
    conn = sqlite3.connect(db.path)
    conn.executescript('BEGIN;' + SCHEMA + 'COMMIT;')
    for target in (2, 3, 4):
        conn.executescript('BEGIN;' + MIGRATIONS[target] + 'COMMIT;')
    conn.execute("INSERT INTO usuarios(id,nome,nome_chave,senha_hash) VALUES(1,'Clayton','clayton','x')")
    conn.execute("INSERT INTO imagens(id,usuario_id,tipo,largura,altura,bytes) VALUES('" + 'a' * 64 + "',1,'avatar',10,10,10)")
    conn.execute("UPDATE usuarios SET avatar_id='" + 'a' * 64 + "' WHERE id=1")
    conn.execute("INSERT INTO jogos(usuario_id,nome,nome_chave,plataforma,progresso) VALUES(1,'B','b','PC',10)")
    conn.execute("INSERT INTO jogos(usuario_id,nome,nome_chave,plataforma,progresso) VALUES(1,'A','a','PC',20)")
    conn.commit(); conn.close()
    db.initialize()
    with db.connection() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION == 7
        rows = [dict(r) for r in conn.execute('SELECT nome, posicao, ainda_jogando, trofeus_fonte FROM jogos ORDER BY posicao')]
        assert [r['nome'] for r in rows] == ['B', 'A'] and rows[0]['posicao'] == 1 and rows[0]['ainda_jogando'] == 0 and rows[0]['trofeus_fonte'] == ''
        assert dict(conn.execute('SELECT usuario_id, posicao, imagem_id FROM avatares').fetchone()) == {'usuario_id': 1, 'posicao': 1, 'imagem_id': 'a' * 64}
        assert conn.execute('SELECT preferencias FROM usuarios').fetchone()[0] == '{}'
