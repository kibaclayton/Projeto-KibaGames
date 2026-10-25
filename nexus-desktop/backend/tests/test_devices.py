import sqlite3

from fastapi.testclient import TestClient
from nexus_backend import database
from nexus_backend.api import create_app


def login(client, name='Clayton', remember=True, device='Celular de teste'):
    created = client.post('/api/perfis', json={'nome': name, 'senha': 'senha-teste-123'})
    if created.status_code == 409:
        created = type('R', (), {'json': lambda self: next(p for p in client.get('/api/perfis').json() if p['nome'] == name)})()
    session = client.post('/api/sessao', json={'perfil_id': created.json()['id'], 'senha': 'senha-teste-123', 'lembrar': remember, 'aparelho': device})
    assert session.status_code == 200, session.text
    return session.json()


def auth(session):
    return {'Authorization': 'Bearer ' + session['token']}


def test_remembered_device_logs_in_without_password_and_rotates_its_credential(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        plain = login(client, remember=False)
        assert plain['aparelho_token'] is None and plain['aparelho_id'] is None
        session = login(client, device='Pixel 8 · Chrome')
        token, device_id = session['aparelho_token'], session['aparelho_id']
        assert token and len(token) >= 40 and device_id
        renewed = client.post('/api/sessao/aparelho', json={'token': token})
        assert renewed.status_code == 200, renewed.text
        assert renewed.json()['perfil']['nome'] == 'Clayton' and renewed.json()['aparelho_id'] == device_id
        assert renewed.json()['aparelho_token'] != token, 'the credential rotates on every use'
        assert client.get('/api/conta', headers=auth(renewed.json())).status_code == 200
        grace = client.post('/api/sessao/aparelho', json={'token': token})
        assert grace.status_code == 200 and grace.json()['aparelho_token'] is None, 'right after rotation the old credential still opens a session, without a new credential'
        assert client.get('/api/conta', headers=auth(grace.json())).status_code == 200
        with sqlite3.connect(tmp_path / 'nexus.sqlite3') as conn:
            conn.execute("UPDATE aparelhos SET rotacionado='2000-01-01T00:00:00.000Z'")
        assert client.post('/api/sessao/aparelho', json={'token': token}).status_code == 401, 'after the grace window a copied old credential stops working'
        again = client.post('/api/sessao/aparelho', json={'token': renewed.json()['aparelho_token']})
        assert again.status_code == 200
        with sqlite3.connect(tmp_path / 'nexus.sqlite3') as conn:
            stored = conn.execute('SELECT token_hash FROM aparelhos').fetchall()
        assert len(stored) == 1 and again.json()['aparelho_token'] not in stored[0][0], 'only a hash is kept'


def test_devices_survive_restart_while_sessions_do_not(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        session = login(client)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/conta', headers=auth(session)).status_code == 401
        renewed = client.post('/api/sessao/aparelho', json={'token': session['aparelho_token']})
        assert renewed.status_code == 200 and renewed.json()['perfil']['id'] == session['perfil']['id']


def test_listing_forgetting_isolation_and_expiry(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        mine = login(client, device='Meu celular')
        other = login(client, name='Outra pessoa', device='Outro aparelho')
        listed = client.get('/api/conta/aparelhos', headers=auth(mine)).json()
        assert [d['nome'] for d in listed] == ['Meu celular'] and listed[0]['id'] == mine['aparelho_id']
        assert client.delete(f"/api/conta/aparelhos/{mine['aparelho_id']}", headers=auth(other)).status_code == 404, 'another profile cannot forget my device'
        assert client.delete(f"/api/conta/aparelhos/{mine['aparelho_id']}", headers=auth(mine)).status_code == 204
        assert client.post('/api/sessao/aparelho', json={'token': mine['aparelho_token']}).status_code == 401
        assert client.get('/api/conta/aparelhos', headers=auth(mine)).json() == []
        second = login(client, device='Segundo')
        third = login(client, device='Terceiro')
        with sqlite3.connect(tmp_path / 'nexus.sqlite3') as conn:
            conn.execute("UPDATE aparelhos SET expira='2000-01-01T00:00:00.000Z' WHERE id=?", (second['aparelho_id'],))
        assert client.post('/api/sessao/aparelho', json={'token': second['aparelho_token']}).status_code == 401, 'expired credentials are refused'
        assert [d['nome'] for d in client.get('/api/conta/aparelhos', headers=auth(third)).json()] == ['Terceiro']
        assert client.delete('/api/conta/aparelhos', headers=auth(third)).status_code == 204
        assert client.post('/api/sessao/aparelho', json={'token': third['aparelho_token']}).status_code == 401
        assert client.post('/api/sessao/aparelho', json={'token': 'x' * 43}).status_code == 401
        assert client.post('/api/sessao/aparelho', json={'token': 'curto'}).status_code == 422


def test_password_change_forgets_every_device(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        session = login(client)
        changed = client.put('/api/conta/senha', headers=auth(session), json={'senha_atual': 'senha-teste-123', 'nova_senha': 'nova-senha-456', 'confirmar_senha': 'nova-senha-456'})
        assert changed.status_code == 204
        assert client.post('/api/sessao/aparelho', json={'token': session['aparelho_token']}).status_code == 401


def test_existing_version_1_database_is_upgraded_in_place(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    path = tmp_path / 'nexus.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.executescript(database.SCHEMA)
        conn.execute("INSERT INTO usuarios(nome,nome_chave,senha_hash) VALUES('Antigo','antigo','00'||substr(hex(zeroblob(15)),1,30)||':'||hex(zeroblob(32)))")
    database.Database(tmp_path).initialize()
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == database.SCHEMA_VERSION
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='aparelhos'").fetchone()[0] == 1
        assert 'hash_anterior' in [c[1] for c in conn.execute('PRAGMA table_info(aparelhos)')], 'every migration step is applied in order'
        assert conn.execute('SELECT nome FROM usuarios').fetchone()[0] == 'Antigo', 'existing rows are preserved'
    database.Database(tmp_path).initialize()  # idempotent
