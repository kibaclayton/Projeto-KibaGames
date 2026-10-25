import hashlib
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient
from nexus_backend import runtime, updates
from nexus_backend.api import create_app


def make_package(channel, build, exe_name='NexusWolfs.exe', manifest_build=None, corrupt=False):
    channel.mkdir(parents=True, exist_ok=True)
    name = f'NexusWolfs-0.3.0-{build}.zip'
    path = channel / name
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(exe_name, b'MZ fake exe ' + build.encode())
        archive.writestr('versao.json', json.dumps({'versao': '0.3.0', 'build': build, 'exe': exe_name}))
        archive.writestr('_internal/frontend/index.html', '<html>Nexus Wolf</html>')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (channel / 'atualizacao.json').write_text(json.dumps({'versao': '0.3.0', 'build': manifest_build or build, 'arquivo': name, 'sha256': 'f' * 64 if corrupt else digest, 'tamanho': path.stat().st_size}), encoding='utf-8')
    return path


def make_install(tmp_path, build='20260101-000000'):
    app_dir = tmp_path / 'Nexus Wolfs'
    app_dir.mkdir()
    (app_dir / 'NexusWolfs.exe').write_bytes(b'MZ current')
    (app_dir / 'versao.json').write_text(json.dumps({'versao': '0.3.0', 'build': build, 'exe': 'NexusWolfs.exe'}), encoding='utf-8')
    (app_dir / 'instalado.json').write_text(json.dumps({'instalado': True, 'build': build, 'dados_anteriores': 'C:/antigo', 'canal': 'C:/canal'}), encoding='utf-8')
    (app_dir / 'unins000.exe').write_bytes(b'MZ uninstaller')
    (app_dir / 'unins000.dat').write_bytes(b'dat')
    return app_dir


def test_check_prepare_and_apply_follow_the_manifest_hash_and_self_test(tmp_path):
    app_dir = make_install(tmp_path)
    channel = tmp_path / 'canal'
    make_package(channel, '20260202-000000')
    verified, spawned = [], []
    updater = updates.Updater(app_dir, tmp_path / 'dados', {'versao': '0.3.0', 'build': '20260101-000000'}, str(channel), 'NexusWolfs.exe',
                              verify=lambda exe, data: verified.append((exe, data)) or {'status': 'ok'}, spawn=lambda command, **kw: spawned.append(command))
    assert updater.status()['preparada'] is None and updater.status()['anterior'] is None
    found = updater.check()
    assert found['nova'] is True and found['build'] == '20260202-000000'
    staged = updater.prepare()
    assert staged['pasta'] == str(tmp_path / 'Nexus Wolfs.novo') and (tmp_path / 'Nexus Wolfs.novo' / 'NexusWolfs.exe').is_file()
    assert verified and verified[0][0] == tmp_path / 'Nexus Wolfs.novo' / 'NexusWolfs.exe', 'the new executable is self-tested before it can be applied'
    assert (tmp_path / 'dados' / 'atualizacoes' / 'NexusWolfs-0.3.0-20260202-000000.zip').is_file()
    assert updater.status()['preparada']['build'] == '20260202-000000'
    staged_dir = tmp_path / 'Nexus Wolfs.novo'
    assert (staged_dir / 'unins000.exe').is_file() and (staged_dir / 'unins000.dat').is_file(), 'the Inno uninstaller keeps working after an update'
    marker = json.loads((staged_dir / 'instalado.json').read_text(encoding='utf-8'))
    assert marker['instalado'] is True and marker['build'] == '20260202-000000' and marker['canal'] == 'C:/canal' and marker['dados_anteriores'] == 'C:/antigo', 'the install marker survives with the new build id'
    applied = updater.apply()
    assert applied['aplicando'] == '20260202-000000' and spawned, 'applying hands over to the external script'
    command = spawned[0]
    assert '-Instalacao' in command and str(app_dir) in command and str(tmp_path / 'Nexus Wolfs.novo') in command and '-Reverter' not in command
    assert command[command.index('-Exe') + 1] == 'NexusWolfs.exe'
    assert '-ProcessId' in command and '-Pid' not in command, '$PID is a read-only PowerShell automatic variable; a -Pid parameter would abort the script'


def test_same_or_older_build_is_not_offered_and_missing_channel_is_reported(tmp_path):
    app_dir = make_install(tmp_path, build='20260303-000000')
    channel = tmp_path / 'canal'
    make_package(channel, '20260202-000000')
    updater = updates.Updater(app_dir, tmp_path / 'dados', {'versao': '0.3.0', 'build': '20260303-000000'}, str(channel), 'NexusWolfs.exe', verify=lambda *a: {'status': 'ok'}, spawn=lambda *a, **k: None)
    assert updater.check()['nova'] is False
    with pytest.raises(ValueError, match='Verifique'):
        updater.prepare()
    empty = updates.Updater(app_dir, tmp_path / 'dados', {'build': '1'}, str(tmp_path / 'vazio'), 'NexusWolfs.exe')
    with pytest.raises(ValueError):
        empty.check()
    assert 'canal' in empty.status()['erro']
    unconfigured = updates.Updater(app_dir, tmp_path / 'dados', {'build': '1'}, None, 'NexusWolfs.exe')
    assert unconfigured.status()['canal_configurado'] is False


def test_corrupted_package_or_failed_self_test_leaves_nothing_staged(tmp_path):
    app_dir = make_install(tmp_path)
    channel = tmp_path / 'canal'
    make_package(channel, '20260202-000000', corrupt=True)
    updater = updates.Updater(app_dir, tmp_path / 'dados', {'build': '20260101-000000'}, str(channel), 'NexusWolfs.exe', verify=lambda *a: {'status': 'ok'}, spawn=lambda *a, **k: None)
    updater.check()
    with pytest.raises(ValueError, match='corrompido'):
        updater.prepare()
    assert not (tmp_path / 'Nexus Wolfs.novo').exists() and not list((tmp_path / 'dados' / 'atualizacoes').glob('*.zip'))
    make_package(channel, '20260202-000000')

    def failing(exe, data):
        raise ValueError('A versão nova falhou no autoteste e não será aplicada.')
    strict = updates.Updater(app_dir, tmp_path / 'dados', {'build': '20260101-000000'}, str(channel), 'NexusWolfs.exe', verify=failing, spawn=lambda *a, **k: None)
    strict.check()
    with pytest.raises(ValueError, match='autoteste'):
        strict.prepare()
    assert not (tmp_path / 'Nexus Wolfs.novo').exists() and strict.status()['preparada'] is None
    with pytest.raises(ValueError, match='Nenhuma'):
        strict.apply()


def test_rollback_needs_a_previous_version_and_calls_the_script_in_revert_mode(tmp_path):
    app_dir = make_install(tmp_path)
    spawned = []
    updater = updates.Updater(app_dir, tmp_path / 'dados', {'build': '2'}, None, 'NexusWolfs.exe', spawn=lambda command, **kw: spawned.append(command))
    with pytest.raises(ValueError, match='anterior'):
        updater.rollback()
    previous = tmp_path / 'Nexus Wolfs.anterior'
    previous.mkdir()
    (previous / 'NexusWolfs.exe').write_bytes(b'MZ old')
    (previous / 'versao.json').write_text(json.dumps({'versao': '0.3.0', 'build': '1'}), encoding='utf-8')
    assert updater.status()['anterior']['build'] == '1'
    assert updater.rollback()['revertendo'] is True and '-Reverter' in spawned[0]


def test_installed_mode_imports_the_portable_library_once(tmp_path):
    source = tmp_path / 'portatil'
    (source / 'images').mkdir(parents=True)
    (source / 'certificados').mkdir()
    (source / 'images' / 'a.webp').write_bytes(b'img')
    (source / 'certificados' / 'nexus-ca.crt').write_bytes(b'cert')
    (source / 'acesso-rede.json').write_text('{"ativo": true, "porta": 8443}', encoding='utf-8')
    (source / 'backups').mkdir()
    (source / 'backups' / 'x.zip').write_bytes(b'zip')
    with sqlite3.connect(source / 'nexus.sqlite3') as conn:
        conn.execute('CREATE TABLE t(x)')
        conn.execute("INSERT INTO t VALUES('dado')")
    target = tmp_path / 'instalado'
    assert runtime.import_previous_data(target, source) is True
    with sqlite3.connect(target / 'nexus.sqlite3') as conn:
        assert conn.execute('SELECT x FROM t').fetchone()[0] == 'dado'
    assert (target / 'images' / 'a.webp').is_file() and (target / 'certificados' / 'nexus-ca.crt').is_file() and (target / 'acesso-rede.json').is_file()
    assert not (target / 'backups').exists(), 'backups stay with the portable library'
    assert json.loads((target / 'importacao.json').read_text(encoding='utf-8'))['origem'] == str(source)
    assert runtime.import_previous_data(target, source) is False, 'never overwrites an existing installed library'
    assert runtime.import_previous_data(tmp_path / 'outro', tmp_path / 'inexistente') is False
    app_dir = tmp_path / 'app'
    app_dir.mkdir()
    assert runtime.install_info(app_dir) is None and runtime.version_info(app_dir)['build'] == 'dev'
    (app_dir / 'instalado.json').write_text(json.dumps({'instalado': True, 'build': '9', 'dados': str(target)}), encoding='utf-8')
    (app_dir / 'versao.json').write_text(json.dumps({'versao': '0.3.0', 'build': '9'}), encoding='utf-8-sig')  # com BOM, como o PowerShell 5.1 grava
    assert runtime.installed_data_directory(runtime.install_info(app_dir)) == target and runtime.version_info(app_dir)['build'] == '9'


def test_manifest_and_version_files_with_utf8_bom_are_accepted(tmp_path):
    app_dir = make_install(tmp_path)
    channel = tmp_path / 'canal'
    make_package(channel, '20260202-000000')
    with_bom = (channel / 'atualizacao.json').read_bytes()
    (channel / 'atualizacao.json').write_bytes(b'\xef\xbb\xbf' + with_bom)
    updater = updates.Updater(app_dir, tmp_path / 'dados', {'build': '20260101-000000'}, str(channel), 'NexusWolfs.exe', verify=lambda *a: {'status': 'ok'}, spawn=lambda *a, **k: None)
    assert updater.check()['nova'] is True
    assert updater.prepare()['build'] == '20260202-000000'


def test_update_endpoints_require_the_installed_app_and_this_computer(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, client=('127.0.0.1', 1)) as client:
        created = client.post('/api/perfis', json={'nome': 'Clayton', 'senha': 'senha-teste-123'}).json()
        token = client.post('/api/sessao', json={'perfil_id': created['id'], 'senha': 'senha-teste-123'}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        status = client.get('/api/atualizacao', headers=headers).json()
        assert status['instalado'] is False and status['build'] == 'dev' and status['canal_configurado'] is False
        assert client.post('/api/atualizacao/verificar', headers=headers).status_code == 404
        assert client.get('/api/saude').json()['build'] == 'dev'
        spawned = []
        app.state.updater = updates.Updater(make_install(tmp_path), tmp_path, {'versao': '0.3.0', 'build': '20260101-000000'}, str(tmp_path / 'canal'), 'NexusWolfs.exe', verify=lambda *a: {'status': 'ok'}, spawn=lambda command, **kw: spawned.append(command))
        app.state.runtime['instalado'] = True
        make_package(tmp_path / 'canal', '20260505-000000')
        assert client.post('/api/atualizacao/verificar', headers=headers).json()['nova'] is True
        assert client.post('/api/atualizacao/aplicar', headers=headers).status_code == 409, 'nothing prepared yet'
        assert client.post('/api/atualizacao/preparar', headers=headers).status_code == 200
        closed = []
        app.state.shutdown = lambda: closed.append(True)
        applied = client.post('/api/atualizacao/aplicar', headers=headers)
        assert applied.status_code == 200 and applied.json()['fechando'] is True and spawned
    with TestClient(app, client=('192.168.1.9', 1)) as remote:
        assert remote.get('/api/atualizacao', headers=headers).status_code in (401, 403)
