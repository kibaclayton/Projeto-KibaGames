import io
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from nexus_backend.api import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        yield client


def profile(client, name='Clayton'):
    created = client.post('/api/perfis', json={'nome': name, 'senha': 'senha-teste-123'})
    assert created.status_code == 201, created.text
    session = client.post('/api/sessao', json={'perfil_id': created.json()['id'], 'senha': 'senha-teste-123'})
    assert session.status_code == 200
    return created.json(), {'Authorization': 'Bearer ' + session.json()['token']}


def image_bytes(size=(600, 900)):
    stream = io.BytesIO()
    Image.new('RGB', size, '#a63ab7').save(stream, 'PNG')
    return stream.getvalue()


def test_profiles_login_password_and_revocation(client):
    user, headers = profile(client)
    assert client.get('/api/perfis').json() == [{'id': user['id'], 'nome': 'Clayton', 'avatar_id': None}]
    assert client.get('/api/resumo').status_code == 401
    assert client.post('/api/sessao', json={'perfil_id': user['id'], 'senha': 'errada'}).status_code == 401
    changed = client.put('/api/conta/senha', headers=headers, json={'senha_atual': 'senha-teste-123', 'nova_senha': 'nova-senha-456', 'confirmar_senha': 'nova-senha-456'})
    assert changed.status_code == 204
    assert client.get('/api/conta', headers=headers).status_code == 401
    assert client.post('/api/sessao', json={'perfil_id': user['id'], 'senha': 'senha-teste-123'}).status_code == 401
    new = client.post('/api/sessao', json={'perfil_id': user['id'], 'senha': 'nova-senha-456'}).json()
    h = {'Authorization': 'Bearer ' + new['token']}
    assert client.delete('/api/sessao', headers=h).status_code == 204
    assert client.get('/api/resumo', headers=h).status_code == 401


def test_profile_duplicates_validation_redaction_rate_limit(client):
    user, headers = profile(client, 'Álvaro')
    assert client.post('/api/perfis', json={'nome': 'alvaro', 'senha': 'senha-teste-123'}).status_code == 409
    invalid = client.post('/api/perfis', json={'nome': 'Outra', 'senha': 'segredo'})
    assert invalid.status_code == 422
    assert 'segredo' not in invalid.text
    for _ in range(5):
        assert client.post('/api/sessao', json={'perfil_id': user['id'], 'senha': 'errada'}).status_code == 401
    assert client.post('/api/sessao', json={'perfil_id': user['id'], 'senha': 'errada'}).status_code == 429


def test_game_crud_rules_and_profile_isolation(client):
    _, owner = profile(client)
    _, other = profile(client, 'Outra pessoa')
    created = client.post('/api/jogos', headers=owner, json={'nome': 'Alan Wake 2', 'progresso': 65, 'trofeus_obtidos': 10, 'trofeus_total': 20,
                         'notas': 'Capítulo 2', 'cronograma': {'2026-09-07': 'single', '2026-09-08': 'range'}})
    assert created.status_code == 201, created.text
    game = created.json()
    assert game['trofeus_percentual'] == 50 and not game['platinado']
    path = '/api/jogos/' + str(game['id'])
    assert client.get(path, headers=other).status_code == 404
    assert client.patch(path, headers=other, json={'favorito': True}).status_code == 404
    assert client.delete(path, headers=other).status_code == 404
    assert client.get('/api/jogos', headers=other).json()['total'] == 0
    changed = client.patch(path, headers=owner, json={'favorito': True}).json()
    assert changed['favorito'] and changed['notas'] == 'Capítulo 2'
    assert changed['cronograma'] == game['cronograma']
    for patch in [{'trofeus_obtidos': 21}, {'progresso': 101}, {'usuario_id': 2}, {'data_inicio': '2026-09-10', 'data_termino': '2026-09-01'}, {'cronograma': {'errada': 'single'}}]:
        assert client.patch(path, headers=owner, json=patch).status_code == 422
    assert client.get(path, headers=owner).json()['progresso'] == 65
    assert client.delete(path, headers=owner).status_code == 204
    assert client.get(path, headers=owner).status_code == 404


def test_search_pagination_highlights_and_zero_trophies(client):
    _, h = profile(client)
    for name, value, status, genre in [('Áção 100%', 80, '', 'Ação'), ('Áção dois', 10, '', 'RPG'), ('Zerado', 100, '', 'RPG'), ('Pendente', 0, '', ''), ('Pausado', 95, 'Pausado', '')]:
        result = client.post('/api/jogos', headers=h, json={'nome': name, 'progresso': value, 'status_avancado': status, 'genero': genre})
        assert result.status_code == 201
        assert not result.json()['platinado']  # 0/0 never means platinum.
    assert [g['progresso'] for g in client.get('/api/destaques', headers=h).json()] == [80, 10]
    assert client.get('/api/jogos', headers=h, params={'busca': 'ACAO'}).json()['total'] == 2
    assert client.get('/api/jogos', headers=h, params={'busca': 'ACAO', 'genero': 'RPG'}).json()['total'] == 1
    assert client.get('/api/jogos', headers=h, params={'busca': '%'}).json()['total'] == 1
    page = client.get('/api/jogos', headers=h, params={'limite': 2, 'pagina': 2}).json()
    assert len(page['itens']) == 2 and page['total'] == 5
    assert 'notas' not in page['itens'][0] and 'capa' not in page['itens'][0]
    assert client.get('/api/jogos', headers=h, params={'limite': 101}).status_code == 422


def test_collections_delete_keeps_games_and_blocks_foreign_links(client):
    _, h = profile(client)
    _, other = profile(client, 'Outro')
    collection = client.post('/api/colecoes', headers=h, json={'nome': 'Resident Evil'}).json()
    foreign = client.post('/api/colecoes', headers=other, json={'nome': 'Outra'}).json()
    game = client.post('/api/jogos', headers=h, json={'nome': 'Resident Evil 2', 'colecao_id': collection['id']}).json()
    assert client.patch(f'/api/jogos/{game["id"]}', headers=h, json={'colecao_id': foreign['id']}).status_code == 404
    assert client.get('/api/colecoes', headers=h).json()[0]['total'] == 1
    assert client.put(f'/api/colecoes/{collection["id"]}', headers=h, json={'nome': 'RE'}).status_code == 200
    assert client.delete(f'/api/colecoes/{collection["id"]}', headers=other).status_code == 404
    assert client.delete(f'/api/colecoes/{collection["id"]}', headers=h).status_code == 204
    saved = client.get(f'/api/jogos/{game["id"]}', headers=h).json()
    assert saved['colecao_id'] is None and saved['nome'] == 'Resident Evil 2'


def test_upload_conversion_deduplication_ownership_and_avatar(client):
    user, h = profile(client)
    _, other = profile(client, 'Outro')
    uploaded = client.post('/api/imagens?tipo=capa', headers=h, content=image_bytes())
    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()
    assert client.post('/api/imagens?tipo=capa', headers=h, content=image_bytes()).json()['id'] == image['id']
    assert client.get('/api/imagens/' + image['id'], headers=other).status_code == 404
    thumb = client.get('/api/imagens/' + image['id'] + '?miniatura=true', headers=h)
    with Image.open(io.BytesIO(thumb.content)) as output:
        assert output.format == 'WEBP' and output.height <= 320 and output.width <= 240
    assert client.post('/api/jogos', headers=other, json={'nome': 'Inválido', 'capa_id': image['id']}).status_code == 404
    assert client.put('/api/conta/avatar', headers=h, json={'imagem_id': image['id']}).status_code == 422
    avatar = client.post('/api/imagens?tipo=avatar&x=10&y=20&largura=200&altura=200', headers=h, content=image_bytes()).json()
    assert avatar['largura'] == avatar['altura'] == 200
    assert client.put('/api/conta/avatar', headers=h, json={'imagem_id': avatar['id']}).status_code == 200
    assert client.get(f'/api/perfis/{user["id"]}/avatar').headers['content-type'] == 'image/webp'
    assert client.post('/api/imagens?x=1', headers=h, content=image_bytes()).status_code == 422
    assert client.post('/api/imagens?x=9999&y=0&largura=20&altura=20', headers=h, content=image_bytes()).status_code == 422
    assert client.post('/api/imagens', headers=h, content=b'not an image').status_code == 422


def test_foreign_origin_host_and_body_limit(client):
    payload = {'nome': 'Bloqueado', 'senha': 'senha-1234'}
    assert client.post('/api/perfis', headers={'Origin': 'https://evil.example'}, json=payload).status_code == 403
    assert client.get('/api/saude', headers={'Host': 'evil.example'}).status_code == 400
    assert client.get('/api/perfis').json() == []
    assert client.post('/api/perfis', content=b'x' * (1024 * 1024 + 1)).status_code == 413
    assert client.options('/api/sessao', headers={'Origin': 'http://127.0.0.1:1420', 'Access-Control-Request-Method': 'POST'}).status_code == 200


def test_persistence_after_restart(tmp_path):
    with TestClient(create_app(tmp_path)) as first:
        user, h = profile(first)
        first.post('/api/jogos', headers=h, json={'nome': 'Persistente'})
    with TestClient(create_app(tmp_path)) as second:
        assert second.get('/api/resumo', headers=h).status_code == 401
        login = second.post('/api/sessao', json={'perfil_id': user['id'], 'senha': 'senha-teste-123'}).json()
        fresh = {'Authorization': 'Bearer ' + login['token']}
        assert second.get('/api/jogos', headers=fresh).json()['itens'][0]['nome'] == 'Persistente'
