"""Esqueci a senha: redefinição só deste computador, com confirmação, revogando sessões e aparelhos lembrados."""
from fastapi.testclient import TestClient
from nexus_backend.api import create_app


def make_profile(client, name='Clayton'):
    created = client.post('/api/perfis', json={'nome': name, 'senha': 'senha-antiga-123'})
    assert created.status_code == 201, created.text
    return created.json()['id']


def test_reset_is_refused_from_the_network_but_works_on_this_computer(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, client=('192.168.15.50', 5000)) as phone:
        user = make_profile(phone)
        refused = phone.put(f'/api/perfis/{user}/redefinir-senha', json={'nova_senha': 'senha-nova-456', 'confirmar_senha': 'senha-nova-456'})
        assert refused.status_code == 403 and 'neste computador' in refused.json()['detail']
        assert phone.post('/api/sessao', json={'perfil_id': user, 'senha': 'senha-antiga-123'}).status_code == 200, 'the old password still works after a refused reset'
    with TestClient(app, client=('127.0.0.1', 5000)) as local:
        remembered = local.post('/api/sessao', json={'perfil_id': user, 'senha': 'senha-antiga-123', 'lembrar': True, 'aparelho': 'Celular'}).json()
        headers = {'Authorization': 'Bearer ' + remembered['token']}
        assert local.get('/api/conta', headers=headers).status_code == 200
        assert local.put(f'/api/perfis/{user}/redefinir-senha', json={'nova_senha': 'senha-nova-456', 'confirmar_senha': 'diferente-456'}).status_code == 422
        assert local.put(f'/api/perfis/{user}/redefinir-senha', json={'nova_senha': 'curta', 'confirmar_senha': 'curta'}).status_code == 422
        assert local.put('/api/perfis/999/redefinir-senha', json={'nova_senha': 'senha-nova-456', 'confirmar_senha': 'senha-nova-456'}).status_code == 404
        done = local.put(f'/api/perfis/{user}/redefinir-senha', json={'nova_senha': 'senha-nova-456', 'confirmar_senha': 'senha-nova-456'})
        assert done.status_code == 204, done.text
        assert local.get('/api/conta', headers=headers).status_code == 401, 'every session of the profile is revoked'
        assert local.post('/api/sessao/aparelho', json={'token': remembered['aparelho_token']}).status_code == 401, 'remembered devices are forgotten'
        assert local.post('/api/sessao', json={'perfil_id': user, 'senha': 'senha-antiga-123'}).status_code == 401
        session = local.post('/api/sessao', json={'perfil_id': user, 'senha': 'senha-nova-456'})
        assert session.status_code == 200
        assert local.get('/api/conta/aparelhos', headers={'Authorization': 'Bearer ' + session.json()['token']}).json() == []


def test_reset_is_rate_limited_per_profile_and_never_echoes_the_password(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 5000)) as local:
        user = make_profile(local)
        other = make_profile(local, 'Juan')
        body = {'nova_senha': 'senha-nova-456', 'confirmar_senha': 'senha-nova-456'}
        for _ in range(3):
            assert local.put(f'/api/perfis/{user}/redefinir-senha', json=body).status_code == 204
        limited = local.put(f'/api/perfis/{user}/redefinir-senha', json=body)
        assert limited.status_code == 429 and 'senha-nova' not in limited.text
        assert local.put(f'/api/perfis/{other}/redefinir-senha', json=body).status_code == 204, 'the limit is per profile'
        invalid = local.put(f'/api/perfis/{other}/redefinir-senha', json={'nova_senha': 'segredo-grande-1', 'confirmar_senha': 'segredo-grande-2'})
        assert invalid.status_code == 422 and 'segredo-grande' not in invalid.text, 'validation errors never reflect the submitted password'
