from fastapi.testclient import TestClient
from nexus_backend.api import create_app


def test_bundled_frontend_is_served_without_exposing_data(tmp_path):
    public = tmp_path / 'frontend'
    public.mkdir()
    (public / 'index.html').write_text('<html>NEXUS FRONTEND</html>')
    (public / 'assets').mkdir()
    (public / 'assets' / 'test.js').write_text('console.log("app")')
    (tmp_path / 'secret.txt').write_text('PRIVATE')
    app = create_app(tmp_path / 'data')
    from nexus_backend import runtime
    attach = getattr(runtime, 'attach_frontend', None)
    assert callable(attach), 'Runtime must serve the packaged frontend'
    attach(app, public)
    with TestClient(app) as client:
        assert 'NEXUS FRONTEND' in client.get('/').text
        assert client.get('/assets/test.js').status_code == 200
        assert client.get('/api/saude').json()['status'] == 'ok'
        assert client.get('/data/nexus.sqlite3').status_code == 404
        assert 'PRIVATE' not in client.get('/%2e%2e/secret.txt').text


def test_packaged_runtime_prefers_completed_import(tmp_path):
    from nexus_backend import runtime
    choose = getattr(runtime, 'choose_data_directory', None)
    assert callable(choose), 'Runtime must reuse a single stable data directory'
    assert choose(tmp_path) == tmp_path / 'data' / 'biblioteca'
    imported = tmp_path / 'data' / 'biblioteca-importada'
    imported.mkdir(parents=True)
    (imported / 'nexus.sqlite3').touch()
    assert choose(tmp_path) == imported
