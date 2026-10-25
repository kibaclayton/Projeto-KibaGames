import http.client
import json
import socket
import ssl

import pytest
from fastapi.testclient import TestClient
from nexus_backend import network
from nexus_backend.api import create_app


def profile(client, name='Clayton'):
    created = client.post('/api/perfis', json={'nome': name, 'senha': 'senha-teste-123'})
    assert created.status_code == 201, created.text
    session = client.post('/api/sessao', json={'perfil_id': created.json()['id'], 'senha': 'senha-teste-123'})
    assert session.status_code == 200
    return created.json(), {'Authorization': 'Bearer ' + session.json()['token']}


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def loopback_only(app, addresses):
    """Keep the listener on 127.0.0.1 during tests while pretending those are the LAN addresses."""
    access = app.state.network
    access.host = '127.0.0.1'
    access.address_source = lambda: list(addresses)
    access.hostnames = ['meu-pc']
    return access


def test_certificates_are_issued_once_and_reissued_only_when_addresses_change(tmp_path):
    from cryptography import x509
    certs = network.Certificates(tmp_path / 'certificados')
    first = certs.ensure(['192.168.0.10'], ['meu-pc', 'Nome Inválido'])
    for path in (certs.ca_cert, certs.ca_key, certs.server_cert, certs.server_key):
        assert path.is_file(), path
    assert certs.ensure(['192.168.0.10'], ['meu-pc'])['serie'] == first['serie'], 'unchanged addresses must not rotate the certificate'
    changed = certs.ensure(['10.0.0.5', '192.168.0.10'], ['meu-pc'])
    assert changed['serie'] != first['serie']
    assert changed['ca_impressao'] == first['ca_impressao'], 'the authority installed on phones must stay stable'
    leaf = x509.load_pem_x509_certificate(certs.server_cert.read_bytes())
    authority = x509.load_pem_x509_certificate(certs.ca_cert.read_bytes())
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert {str(ip) for ip in san.get_values_for_type(x509.IPAddress)} == {'10.0.0.5', '192.168.0.10'}
    assert san.get_values_for_type(x509.DNSName) == ['meu-pc']
    assert leaf.issuer == authority.subject
    assert authority.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    assert (leaf.not_valid_after_utc - leaf.not_valid_before_utc).days <= 825, 'iOS rejects longer server certificates'
    assert b'PRIVATE KEY' not in certs.ca_cert.read_bytes()


def test_network_access_is_off_by_default_and_cannot_be_changed_from_the_network(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, client=('192.168.1.9', 50000)) as remote:
        assert remote.get('/api/acesso-rede').status_code == 401
        _, headers = profile(remote)
        status = remote.get('/api/acesso-rede', headers=headers).json()
        assert status['ativo'] is False and status['executando'] is False and status['local'] is False
        assert remote.put('/api/acesso-rede', headers=headers, json={'ativo': True}).status_code == 403
        assert remote.get('/api/acesso-rede/ca.crt').status_code == 404
    assert not (tmp_path / network.SETTINGS_FILE).exists()
    assert not (tmp_path / 'certificados').exists()


def test_enabling_serves_https_with_the_local_authority_and_persists(tmp_path):
    app = create_app(tmp_path)
    access = loopback_only(app, ['127.0.0.1'])
    port = free_port()
    try:
        with TestClient(app, client=('127.0.0.1', 50000)) as local:
            _, headers = profile(local)
            enabled = local.put('/api/acesso-rede', headers=headers, json={'ativo': True, 'porta': port})
            assert enabled.status_code == 200, enabled.text
            status = enabled.json()
            assert status['ativo'] and status['executando'] and status['porta'] == port and status['local']
            assert status['enderecos'] == [f'https://127.0.0.1:{port}', f'https://meu-pc:{port}']
            assert json.loads((tmp_path / network.SETTINGS_FILE).read_text(encoding='utf-8')) == {'ativo': True, 'porta': port}
            authority = local.get('/api/acesso-rede/ca.crt')
            assert authority.status_code == 200 and b'BEGIN CERTIFICATE' in authority.content
            assert 'nexus-ca.crt' in authority.headers['content-disposition']

            trusted = ssl.create_default_context(cadata=authority.text)
            connection = http.client.HTTPSConnection('127.0.0.1', port, context=trusted, timeout=5)
            connection.request('GET', '/api/saude')
            response = connection.getresponse()
            assert response.status == 200 and json.loads(response.read())['status'] == 'ok'
            connection.close()
            with pytest.raises(ssl.SSLError):
                untrusted = http.client.HTTPSConnection('127.0.0.1', port, context=ssl.create_default_context(), timeout=5)
                untrusted.request('GET', '/api/saude')

            with socket.socket() as blocker:
                blocker.bind(('127.0.0.1', 0))
                blocker.listen(1)
                busy = local.put('/api/acesso-rede', headers=headers, json={'ativo': True, 'porta': blocker.getsockname()[1]})
                assert busy.status_code == 409 and 'porta' in busy.json()['detail'].lower()
            assert local.get('/api/acesso-rede', headers=headers).json()['executando'] is False

            disabled = local.put('/api/acesso-rede', headers=headers, json={'ativo': False})
            assert disabled.status_code == 200 and disabled.json()['ativo'] is False and disabled.json()['executando'] is False
            assert json.loads((tmp_path / network.SETTINGS_FILE).read_text(encoding='utf-8'))['ativo'] is False
            with pytest.raises(OSError):
                closed = http.client.HTTPSConnection('127.0.0.1', port, context=trusted, timeout=2)
                closed.request('GET', '/api/saude')
    finally:
        access.stop()


def test_host_and_origin_policy_follow_the_listener(tmp_path):
    app = create_app(tmp_path)
    access = loopback_only(app, ['192.168.50.7'])
    port = free_port()
    with TestClient(app, base_url=f'https://192.168.50.7:{port}', client=('192.168.50.8', 1)) as lan:
        assert lan.get('/api/saude').status_code == 400, 'LAN host must be rejected while access is off'
    try:
        with TestClient(app, client=('127.0.0.1', 1)) as local:
            _, headers = profile(local)
            assert local.put('/api/acesso-rede', headers=headers, json={'ativo': True, 'porta': port}).status_code == 200
            with TestClient(app, base_url=f'https://192.168.50.7:{port}', client=('192.168.50.8', 1)) as lan:
                assert lan.get('/api/saude').status_code == 200
                own = {'Origin': f'https://192.168.50.7:{port}'}
                assert lan.post('/api/perfis', json={'nome': 'Celular', 'senha': 'senha-teste-123'}, headers=own).status_code == 201
                foreign = {'Origin': 'https://evil.example'}
                assert lan.post('/api/perfis', json={'nome': 'Intruso', 'senha': 'senha-teste-123'}, headers=foreign).status_code == 403
            with TestClient(app, base_url=f'https://meu-pc:{port}', client=('192.168.50.8', 1)) as named:
                assert named.get('/api/saude').status_code == 200
            with TestClient(app, base_url='https://evil.example', client=('192.168.50.8', 1)) as evil:
                assert evil.get('/api/saude').status_code == 400
            access.stop()
            with TestClient(app, base_url=f'https://192.168.50.7:{port}', client=('192.168.50.8', 1)) as lan:
                assert lan.get('/api/saude').status_code == 400, 'stopping the listener closes the host allowlist again'
    finally:
        access.stop()


def test_settings_survive_restart_and_start_if_enabled_reports_errors(tmp_path):
    network.save_settings(tmp_path, {'ativo': True, 'porta': 70000})
    assert network.load_settings(tmp_path) == {'ativo': True, 'porta': network.DEFAULT_PORT}, 'invalid ports fall back to the default'
    (tmp_path / network.SETTINGS_FILE).write_text('{corrompido', encoding='utf-8')
    assert network.load_settings(tmp_path) == {'ativo': False, 'porta': network.DEFAULT_PORT}
    port = free_port()
    network.save_settings(tmp_path, {'ativo': True, 'porta': port})
    app = create_app(tmp_path)
    access = loopback_only(app, [])
    access.start_if_enabled()
    assert access.running is False and 'rede local' in access.error
    access.address_source = lambda: ['127.0.0.1']
    try:
        access.start_if_enabled()
        assert access.running and access.status()['erro'] == ''
    finally:
        access.stop()
