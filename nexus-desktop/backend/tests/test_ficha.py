"""Ficha completa (requisitos, idiomas, classificação indicativa, tempo de jogo, Metacritic, categorias): Steam, IGDB, persistência e migração 6."""
import json
import sqlite3
from fastapi.testclient import TestClient
from nexus_backend import covers, igdb
from nexus_backend.api import create_app
from nexus_backend.database import MIGRATIONS, SCHEMA, SCHEMA_VERSION, Database
from tests.test_api import profile
from tests.test_covers import fake_fetch

STEAM_APP = {'1091500': {'success': True, 'data': {
    'name': 'Cyberpunk 2077', 'genres': [{'description': 'RPG'}], 'release_date': {'date': '10 dez. 2020'}, 'developers': ['CD PROJEKT RED'], 'publishers': ['CD PROJEKT RED'],
    'platforms': {'windows': True}, 'short_description': 'Night City.', 'achievements': {'total': 44},
    'pc_requirements': {'minimum': '<strong>Mínimos:</strong><br><ul class="bb_ul"><li>Requer um processador e sistema operacional de 64 bits<br></li><li><strong>SO:</strong> Windows 10<br></li><li><strong>Processador:</strong> Core i7-6700<br></li></ul>',
                        'recommended': '<strong>Recomendados:</strong><br><ul class="bb_ul"><li><strong>SO:</strong> Windows 10<br></li><li><strong>Placa de vídeo:</strong> GeForce RTX 2060 SUPER &amp; 8 GB<br></li></ul>'},
    'supported_languages': 'Português - Brasil<strong>*</strong>, Inglês<strong>*</strong>, Francês, Inglês<br><strong>*</strong>idiomas com suporte de áudio completo',
    'ratings': {'esrb': {'rating': 'm', 'descriptors': 'Blood and Gore'}, 'dejus': {'rating': '18', 'descriptors': 'Violência extrema, nudez, drogas lícitas', 'required_age': '18'}},
    'metacritic': {'score': 86, 'url': 'https://www.metacritic.com/game/pc/cyberpunk-2077'},
    'categories': [{'id': 2, 'description': 'Um jogador'}, {'id': 28, 'description': 'Suporte total a controle'}, {'id': 22, 'description': 'Conquistas Steam'}],
}}}


def test_steam_details_turn_store_html_into_a_closed_readable_sheet():
    details = covers.steam_details('1091500', fake_fetch({'https://store.steampowered.com/api/appdetails': STEAM_APP}))
    sheet = details['ficha']
    assert sheet['requisitos_minimos'] == 'Requer um processador e sistema operacional de 64 bits\nSO: Windows 10\nProcessador: Core i7-6700'
    assert sheet['requisitos_recomendados'] == 'SO: Windows 10\nPlaca de vídeo: GeForce RTX 2060 SUPER & 8 GB', 'tags gone, entities decoded, label line dropped'
    assert sheet['idiomas'] == ['Português - Brasil (áudio)', 'Inglês (áudio)', 'Francês', 'Inglês']
    assert sheet['classificacao'] == 'ClassInd 18 anos' and sheet['classificacao_detalhe'] == 'Violência extrema, nudez, drogas lícitas', 'the Brazilian rating wins over ESRB'
    assert sheet['metacritic'] == 86 and sheet['categorias'] == ['Um jogador', 'Suporte total a controle', 'Conquistas Steam']
    assert sheet['tempo_historia'] is None, 'Steam does not publish playtime estimates'
    assert set(sheet) == {'requisitos_minimos', 'requisitos_recomendados', 'idiomas', 'classificacao', 'classificacao_detalhe', 'tempo_historia', 'tempo_extras', 'tempo_completo', 'metacritic', 'categorias'}
    assert covers._age_rating({'pegi': {'rating': '18'}}) == ('PEGI 18', '') and covers._age_rating({'dejus': {'rating': 'l'}})[0] == 'ClassInd Livre' and covers._age_rating('x') == ('', '')
    plain = covers.steam_details('1091500', fake_fetch({'https://store.steampowered.com/api/appdetails': {'1091500': {'success': True, 'data': {'name': 'Só nome'}}}}))
    assert plain['ficha']['idiomas'] == [] and plain['ficha']['classificacao'] == '' and plain['ficha']['metacritic'] is None


def test_igdb_adds_time_to_beat_in_minutes():
    config = {'client_id': 'abcdefghij1234567890', 'client_secret': 'secretsecret1234567890'}
    calls = []

    def fake(url, accept, content_types, max_bytes, allowed_hosts=None, seconds=25, method='GET', body=None, headers=None):
        calls.append((url, body))
        if 'id.twitch.tv' in url:
            return 'application/json', json.dumps({'access_token': 'tok', 'expires_in': 3600}).encode()
        if url.endswith('/game_time_to_beats'):
            return 'application/json', json.dumps([{'game_id': 1942, 'hastily': 180000, 'normally': 360000, 'completely': 720000}]).encode()
        return 'application/json', json.dumps([{'id': 1942, 'name': 'The Witcher 3', 'cover': {'image_id': 'co1wyy'}, 'url': 'https://www.igdb.com/games/the-witcher-3'}]).encode()
    raw = igdb.details(config, '1942', fake)
    assert raw['ficha'] == {'tempo_historia': 3000, 'tempo_extras': 6000, 'tempo_completo': 12000}
    assert any(b'where game_id = 1942' in (body or b'') for _, body in calls)
    assert igdb.time_to_beat(config, '1942', lambda *a, **k: (_ for _ in ()).throw(ValueError('fora do ar'))) == {}, 'a failing time query never breaks the sheet'


def test_sheet_is_saved_validated_and_survives_migration_from_schema_5(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        _, headers = profile(client)
        sheet = {'requisitos_minimos': ' SO: Windows 10 \n\n Memória: 12 GB ', 'idiomas': ['Português - Brasil', '', 'Português - Brasil', 'Inglês'], 'classificacao': 'ClassInd 16 anos',
                 'tempo_historia': 1500, 'metacritic': 90, 'categorias': ['Um jogador']}
        created = client.post('/api/jogos', headers=headers, json={'nome': 'Hades', 'ficha': sheet})
        assert created.status_code == 201, created.text
        saved = created.json()['ficha']
        assert saved['requisitos_minimos'] == 'SO: Windows 10\nMemória: 12 GB' and saved['idiomas'] == ['Português - Brasil', 'Inglês'] and saved['tempo_historia'] == 1500
        assert saved['requisitos_recomendados'] == '' and saved['tempo_extras'] is None and saved['classificacao_detalhe'] == ''
        game_id = created.json()['id']
        assert client.get(f'/api/jogos/{game_id}', headers=headers).json()['ficha'] == saved
        patched = client.patch(f'/api/jogos/{game_id}', headers=headers, json={'ficha': {**saved, 'metacritic': 95}}).json()['ficha']
        assert patched['metacritic'] == 95 and patched['idiomas'] == ['Português - Brasil', 'Inglês'], 'a patch replaces the whole sheet with what the editor holds'
        assert client.patch(f'/api/jogos/{game_id}', headers=headers, json={'ficha': {'metacritic': 150}}).status_code == 422
        assert client.patch(f'/api/jogos/{game_id}', headers=headers, json={'ficha': {'tempo_historia': -1}}).status_code == 422
        assert client.patch(f'/api/jogos/{game_id}', headers=headers, json={'ficha': {'css': 'x'}}).status_code == 422, 'unknown keys are refused, never stored'
        listed = client.get('/api/jogos', headers=headers).json()['itens'][0]
        assert 'ficha' not in listed, 'the summary list stays light'
    (tmp_path / 'antiga').mkdir()
    db = Database(tmp_path / 'antiga')
    conn = sqlite3.connect(db.path)
    conn.executescript('BEGIN;' + SCHEMA + 'COMMIT;')
    for target in (2, 3, 4, 5):
        conn.executescript('BEGIN;' + MIGRATIONS[target] + 'COMMIT;')
    conn.execute("INSERT INTO usuarios(id,nome,nome_chave,senha_hash) VALUES(1,'Clayton','clayton','x')")
    conn.execute("INSERT INTO jogos(usuario_id,nome,nome_chave,plataforma,progresso,posicao) VALUES(1,'Control','control','PC',30,1)")
    conn.commit(); conn.close()
    db.initialize()
    with db.connection() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION == 6
        row = dict(conn.execute('SELECT nome, progresso, ficha FROM jogos').fetchone())
    assert row['nome'] == 'Control' and row['progresso'] == 30 and json.loads(row['ficha']) == {}
