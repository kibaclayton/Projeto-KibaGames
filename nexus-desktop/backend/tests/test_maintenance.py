import io
import json
import sqlite3
import zipfile

from PIL import Image
from fastapi.testclient import TestClient
from nexus_backend.api import create_app


def image_bytes(color):
    stream = io.BytesIO()
    Image.new('RGB', (300, 400), color).save(stream, 'PNG')
    return stream.getvalue()


def profile(client, name='Clayton'):
    created = client.post('/api/perfis', json={'nome': name, 'senha': 'senha-teste-123'})
    session = client.post('/api/sessao', json={'perfil_id': created.json()['id'], 'senha': 'senha-teste-123'})
    return {'Authorization': 'Bearer ' + session.json()['token']}


def seed(client, headers):
    cover = client.post('/api/imagens?tipo=capa', headers=headers, content=image_bytes('#a63ab7')).json()['id']
    game = client.post('/api/jogos', headers=headers, json={'nome': 'Alan Wake 2', 'capa_id': cover, 'progresso': 40}).json()
    return game, cover


def test_backup_contains_consistent_snapshot_images_and_verifiable_manifest(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1)) as client:
        headers = profile(client)
        game, cover = seed(client, headers)
        assert client.get('/api/manutencao/backups', headers=headers).json() == {'pasta': str(tmp_path / 'backups'), 'itens': []}
        made = client.post('/api/manutencao/backups', headers=headers)
        assert made.status_code == 201, made.text
        info = made.json()
        assert info['valido'] and info['manifesto']['contagens'] == {'usuarios': 1, 'jogos': 1, 'colecoes': 0, 'imagens': 1} and info['manifesto']['imagens_arquivos'] == 2
        path = tmp_path / 'backups' / info['nome']
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read('manifesto.json'))
            assert {'manifesto.json', 'nexus.sqlite3', f'images/{cover}.webp', f'images/{cover}.thumb.webp'} == names
            assert set(manifest['arquivos']) == names - {'manifesto.json'}
            extracted = tmp_path / 'check.sqlite3'
            extracted.write_bytes(archive.read('nexus.sqlite3'))
        with sqlite3.connect(extracted) as conn:
            assert conn.execute('SELECT nome FROM jogos').fetchone()[0] == 'Alan Wake 2'
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        listed = client.get('/api/manutencao/backups', headers=headers).json()['itens']
        assert [b['nome'] for b in listed] == [info['nome']]
        download = client.get(f"/api/manutencao/backups/{info['nome']}", headers=headers)
        assert download.status_code == 200 and download.headers['content-type'].startswith('application/zip') and len(download.content) == info['bytes']
        assert client.get('/api/manutencao/backups/../../nexus.sqlite3', headers=headers).status_code in (404, 422)
        assert client.delete(f"/api/manutencao/backups/{info['nome']}", headers=headers).status_code == 204
        assert client.get('/api/manutencao/backups', headers=headers).json()['itens'] == []


def test_restore_brings_back_games_and_images_after_a_safety_backup_and_revokes_sessions(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1)) as client:
        headers = profile(client)
        game, cover = seed(client, headers)
        backup = client.post('/api/manutencao/backups', headers=headers).json()['nome']
        assert client.delete(f"/api/jogos/{game['id']}", headers=headers).status_code == 204
        client.post('/api/jogos', headers=headers, json={'nome': 'Jogo novo depois do backup'})
        (tmp_path / 'images' / f'{cover}.webp').unlink()
        restored = client.post(f'/api/manutencao/backups/{backup}/restaurar', headers=headers)
        assert restored.status_code == 200, restored.text
        assert restored.json()['restaurado'] == backup and restored.json()['backup_seguranca'].endswith('-antes-de-restaurar.zip')
        assert client.get('/api/jogos', headers=headers).status_code == 401, 'every session is revoked after a restore'
        headers = {'Authorization': 'Bearer ' + client.post('/api/sessao', json={'perfil_id': 1, 'senha': 'senha-teste-123'}).json()['token']}
        names = [g['nome'] for g in client.get('/api/jogos', headers=headers).json()['itens']]
        assert names == ['Alan Wake 2'], names
        assert (tmp_path / 'images' / f'{cover}.webp').is_file() and client.get(f'/api/imagens/{cover}', headers=headers).status_code == 200
        assert not list(tmp_path.glob('.restaurando-*')) and not list(tmp_path.glob('.anterior-*')), 'no staging folders are left behind'
        assert client.get('/api/manutencao/integridade', headers=headers).json()['ok'] is True
        kinds = sorted(b['manifesto']['motivo'] for b in client.get('/api/manutencao/backups', headers=headers).json()['itens'])
        assert kinds == ['antes-de-restaurar', 'manual']


def test_corrupted_or_foreign_backups_are_refused_without_touching_the_library(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1)) as client:
        headers = profile(client)
        seed(client, headers)
        backup = client.post('/api/manutencao/backups', headers=headers).json()['nome']
        path = tmp_path / 'backups' / backup
        tampered = tmp_path / 'backups' / 'nexus-backup-20200101-000000-x.zip'
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(tampered, 'w') as target:
            for member in source.namelist():
                data = source.read(member)
                target.writestr(member, data + b'x' if member == 'nexus.sqlite3' else data)
        refused = client.post(f'/api/manutencao/backups/{tampered.name}/restaurar', headers=headers)
        assert refused.status_code == 422 and 'corrompido' in refused.json()['detail']
        (tmp_path / 'backups' / 'nexus-backup-20200101-000001-y.zip').write_bytes(b'not a zip')
        assert client.post('/api/manutencao/backups/nexus-backup-20200101-000001-y.zip/restaurar', headers=headers).status_code == 422
        assert client.post('/api/manutencao/backups/nexus-backup-20991231-235959.zip/restaurar', headers=headers).status_code == 404
        assert client.get('/api/jogos', headers=headers).status_code == 200, 'the session survives a refused restore'
        assert client.get('/api/manutencao/integridade', headers=headers).json()['ok'] is True
        listed = client.get('/api/manutencao/backups', headers=headers).json()['itens']
        assert any(not b['valido'] for b in listed), 'invalid files are listed as invalid instead of hidden'


def test_orphan_images_are_counted_and_cleaned_after_a_safety_backup(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1)) as client:
        headers = profile(client)
        game, used = seed(client, headers)
        orphan = client.post('/api/imagens?tipo=capa', headers=headers, content=image_bytes('#113355')).json()['id']
        avatar = client.post('/api/imagens?tipo=avatar', headers=headers, content=image_bytes('#335511')).json()['id']
        client.put('/api/conta/avatar', headers=headers, json={'imagem_id': avatar})
        (tmp_path / 'images' / 'deadbeef.webp').write_bytes(b'stray')
        found = client.get('/api/manutencao/orfas', headers=headers).json()
        assert found['registros'] == 1 and found['arquivos_sem_registro'] == 1 and found['bytes'] > 0
        cleaned = client.post('/api/manutencao/orfas/limpar', headers=headers).json()
        assert cleaned['registros_removidos'] == 1 and cleaned['arquivos_removidos'] == 3 and cleaned['backup_seguranca'].endswith('-antes-de-limpar.zip')
        assert not (tmp_path / 'images' / f'{orphan}.webp').exists() and not (tmp_path / 'images' / 'deadbeef.webp').exists()
        assert (tmp_path / 'images' / f'{used}.webp').is_file() and (tmp_path / 'images' / f'{avatar}.webp').is_file()
        assert client.get(f"/api/jogos/{game['id']}", headers=headers).json()['capa_id'] == used
        assert client.get('/api/manutencao/orfas', headers=headers).json() == {'registros': 0, 'arquivos_sem_registro': 0, 'bytes': 0}


def test_leftover_folders_from_an_interrupted_restore_are_cleaned_on_the_next_listing(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1)) as client:
        headers = profile(client)
        (tmp_path / '.anterior-20260101-000000-images').mkdir()
        (tmp_path / '.anterior-20260101-000000-images' / 'x.webp').write_bytes(b'old')
        (tmp_path / '.restaurando-20260101-000000').mkdir()
        (tmp_path / '.anterior-20260101-000000.sqlite3').write_bytes(b'old')
        assert client.get('/api/manutencao/backups', headers=headers).status_code == 200
        assert not list(tmp_path.glob('.anterior-*')) and not list(tmp_path.glob('.restaurando-*'))


def test_maintenance_is_refused_from_the_network(tmp_path):
    with TestClient(create_app(tmp_path), client=('192.168.1.9', 1)) as remote:
        headers = profile(remote)
        for method, path in (('GET', '/api/manutencao/backups'), ('POST', '/api/manutencao/backups'), ('GET', '/api/manutencao/integridade'), ('GET', '/api/manutencao/orfas'), ('POST', '/api/manutencao/orfas/limpar')):
            assert remote.request(method, path, headers=headers).status_code == 403, path
        assert remote.get('/api/manutencao/backups').status_code == 401
