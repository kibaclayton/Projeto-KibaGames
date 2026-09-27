import io
import json
import sqlite3
from datetime import date
from PIL import Image
import pytest
from nexus_backend import images
from nexus_backend.database import Database
from nexus_backend.migration import migrate_records, snapshot_rows
from nexus_backend.models import Crop
from nexus_backend.security import encode_password, check_password


def picture():
    stream = io.BytesIO()
    Image.new('RGB', (400, 600), 'red').save(stream, 'JPEG')
    return stream.getvalue()


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://example.com/x.png', 'https://user:pass@example.com/x.png', 'https://example.com:444/x.png'])
def test_reject_non_public_url_schemes(url):
    with pytest.raises(ValueError):
        images.validated_address(url)


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
def test_reject_private_dns(monkeypatch, address):
    monkeypatch.setattr(images.socket, 'getaddrinfo', lambda *a, **kw: [(None, None, None, None, (address, 443))])
    with pytest.raises(ValueError):
        images.validated_address('https://image.example/pic.png')


def test_remote_redirect_is_revalidated(monkeypatch):
    addresses = {'public.example': '8.8.8.8', 'private.example': '127.0.0.1'}
    monkeypatch.setattr(images.socket, 'getaddrinfo', lambda host, *a, **kw: [(None, None, None, None, (addresses[host], 443))])
    class Redirect:
        status = 302
        def getheader(self, name, default=None):
            return 'https://private.example/secret' if name == 'Location' else default
    class Connection:
        def __init__(self, host, ip):
            assert host == 'public.example' and ip == '8.8.8.8'
        def request(self, *a, **kw): pass
        def getresponse(self): return Redirect()
        def close(self): pass
    monkeypatch.setattr(images, 'PinnedHTTPS', Connection)
    with pytest.raises(ValueError):
        images.download_image('https://public.example/redirect')


def test_image_limit_and_exif_orientation(monkeypatch):
    source = Image.new('RGB', (120, 80), 'red')
    exif = source.getexif()
    exif[274] = 6
    buf = io.BytesIO()
    source.save(buf, 'JPEG', exif=exif)
    full, _, w, h = images.convert_image(buf.getvalue(), 'capa')
    assert (w, h) == (80, 120)
    with Image.open(io.BytesIO(full)) as converted:
        assert not converted.getexif()
    with pytest.raises(ValueError):
        images.convert_image(buf.getvalue(), 'avatar', Crop(x=0, y=0, width=100, height=100))
    monkeypatch.setattr(images, 'MAX_PIXELS', 100)
    with pytest.raises(ValueError):
        images.convert_image(buf.getvalue(), 'capa')


def records():
    return [
        ('usuarios', {'id': 7, 'nome': 'Clayton', 'senha_hash': encode_password('minha-senha'), 'avatar': picture()}),
        ('colecoes', {'id': 3, 'usuario_id': 7, 'nome': 'Alan Wake'}),
        ('jogos', {'id': 42, 'usuario_id': 7, 'nome': 'Alan Wake 2', 'plataforma': 'PS5', 'progresso': 65,
                   'capa': picture(), 'colecao_id': 3, 'favorito': 1, 'trofeus_obtidos': 8, 'trofeus_total': 20,
                   'data_inicio': date(2026, 9, 7), 'data_termino': None, 'notas': 'Minha nota',
                   'cronograma': json.dumps({'2026-09-07': 'single'}), 'coluna_futura': 'preservar no backup'}),
        ('jogos', {'id': 43, 'usuario_id': 7, 'nome': 'Metro', 'plataforma': 'PC', 'grupo': 'Metro', 'progresso': 0})]


def test_migration_preserves_records_hashes_images_schedule_and_legacy_groups(tmp_path):
    original = records()
    destination = tmp_path / 'importado'
    report = migrate_records(iter(original), destination)
    assert report['integridade'] == 'ok' and not report['mysql_alterado']
    assert report['importados'] == {'usuarios': 1, 'colecoes': 2, 'jogos': 2}
    db = Database(destination)
    with db.connection() as conn:
        user = conn.execute('SELECT * FROM usuarios WHERE id=7').fetchone()
        assert user['senha_hash'] == original[0][1]['senha_hash']
        assert check_password('minha-senha', user['senha_hash'])
        game = conn.execute('SELECT * FROM jogos WHERE id=42').fetchone()
        assert game['favorito'] and game['colecao_id'] == 3 and game['trofeus_total'] == 20
        assert game['data_inicio'] == '2026-09-07' and json.loads(game['cronograma']) == {'2026-09-07': 'single'}
        assert (destination / 'images' / f'{game["capa_id"]}.webp').is_file()
        assert conn.execute('SELECT colecao_id FROM jogos WHERE id=43').fetchone()[0] is not None
    with sqlite3.connect(destination / 'origem-mysql.sqlite3') as conn:
        backup = list(snapshot_rows(conn, 'jogos'))
        assert backup[0]['capa'] == original[2][1]['capa']
        assert backup[0]['coluna_futura'] == 'preservar no backup'
    with pytest.raises(ValueError, match='já existe'):
        migrate_records(iter(original), destination)


def test_invalid_migration_never_publishes_partial_database(tmp_path):
    original = records()
    original[2][1]['usuario_id'] = 999
    destination = tmp_path / 'invalido'
    with pytest.raises(ValueError, match='sem perfil válido'):
        migrate_records(iter(original), destination)
    assert not destination.exists()
    staged = list(tmp_path.glob('invalido.migrando-*'))
    assert len(staged) == 1 and (staged[0] / 'origem-mysql.sqlite3').exists()


def test_database_constraints_prevent_cross_profile_collection(tmp_path):
    db = Database(tmp_path)
    db.initialize()
    with db.connection() as conn:
        conn.executemany('INSERT INTO usuarios(id,nome,nome_chave,senha_hash) VALUES(?,?,?,?)', [(1,'A','a','hash'),(2,'B','b','hash')])
        conn.execute("INSERT INTO colecoes(id,usuario_id,nome,nome_chave) VALUES(1,2,'B','b')")
    with pytest.raises(sqlite3.IntegrityError), db.connection() as conn:
        conn.execute("INSERT INTO jogos(usuario_id,nome,nome_chave,plataforma,colecao_id) VALUES(1,'J','j','PC',1)")
