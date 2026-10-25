from contextlib import asynccontextmanager
import http.client
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Annotated, Literal
import zipfile

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .covers import DETAILS_CACHE_SECONDS, SEARCH_CACHE_SECONDS, SOURCES, Cache, Throttle, download_cover, fetch_preview, game_details, search_covers
from .database import Database, data_directory, normalize
from .images import MAX_BYTES, download_image, store_image
from . import maintenance
from .models import CandidateRef, CollectionInput, Crop, DeviceToken, GameInput, ImageRef, Login, NetworkInput, PasswordChange, PasswordReset, ProfileCreate, RemoteImage
from .network import LOOPBACK, NetworkAccess
from .security import Sessions, check_password, device_login, encode_password, forget_device, forget_devices, list_devices, remember_device
from .service import SUMMARY_COLUMNS, find_duplicate, game_result, owned, save_collection, save_game, validate_image

ORIGINS = ['http://127.0.0.1:1420', 'http://localhost:1420', 'http://127.0.0.1:4173',
           'http://localhost:4173', 'http://127.0.0.1:8765', 'http://localhost:8765',
           'http://tauri.localhost', 'https://tauri.localhost', 'tauri://localhost']
LOCAL_HOSTS = {'127.0.0.1', 'localhost', 'testserver'}


class LocalRequests:
    """Reject unknown hosts and foreign browser origins before mutations; bound body memory for all routes.

    Allowed hosts are the loopback names plus whatever the optional network listener announces while it runs.
    """
    def __init__(self, app, allowed_hosts=lambda: set()):
        self.app = app
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        host = headers.get(b'host', b'').decode('latin1')
        hostname = host.rsplit(':', 1)[0] if ':' in host and not host.endswith(']') else host
        if hostname not in LOCAL_HOSTS and hostname not in self.allowed_hosts():
            return await JSONResponse({'detail': 'Host inválido.'}, status_code=400)(scope, receive, send)
        origin = headers.get(b'origin', b'').decode('latin1')
        own_origin = f"{scope.get('scheme', 'http')}://{host}"
        if origin and origin not in ORIGINS and origin != own_origin:
            return await JSONResponse({'detail': 'Origem não autorizada.'}, status_code=403)(scope, receive, send)
        limit = MAX_BYTES if scope['path'] == '/api/imagens' else 1024 * 1024
        chunks = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunks.extend(message.get('body', b''))
            if len(chunks) > limit:
                return await JSONResponse({'detail': 'Conteúdo excede o limite.'}, status_code=413)(scope, receive, send)
            if not message.get('more_body'):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(chunks), 'more_body': False}
            return await receive()

        async def safe_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([(b'x-content-type-options', b'nosniff'), (b'cache-control', b'no-store')])
            await send(message)
        await self.app(scope, replay, safe_send)


def create_app(directory: Path | None = None):
    db = Database(directory or data_directory())
    sessions = Sessions()

    @asynccontextmanager
    async def lifespan(app):
        db.initialize()
        yield

    app = FastAPI(title="Nexus Wolf’s API local", version='0.3.0', lifespan=lifespan)
    network = NetworkAccess(app, db.directory)
    cover_throttle = Throttle()
    details_throttle = Throttle(limit=40, window=60)
    image_throttle = Throttle(limit=120, window=60)  # prévias e downloads por link: evita uso do serviço como proxy em massa
    search_cache, details_cache = Cache(SEARCH_CACHE_SECONDS), Cache(DETAILS_CACHE_SECONDS)
    device_throttle = Throttle(limit=30, window=60)
    reset_throttle = Throttle(limit=3, window=300)
    app.state.db = db
    app.state.sessions = sessions
    app.state.network = network
    app.state.runtime = {'instalado': False, 'versao': '0.3.0', 'build': 'dev', 'pasta_dados': str(db.directory), 'pasta_app': '', 'importado': False}
    app.state.updater = None  # definido por desktop.py no aplicativo instalado
    app.state.shutdown = None
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET', 'POST', 'PATCH', 'PUT', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])
    app.add_middleware(LocalRequests, allowed_hosts=network.allowed_hosts)
    bearer = HTTPBearer(auto_error=False)

    def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        user_id = sessions.user(credentials.credentials) if credentials and credentials.scheme.lower() == 'bearer' else None
        if user_id is None:
            raise HTTPException(401, 'Selecione seu perfil e entre novamente.', headers={'WWW-Authenticate': 'Bearer'})
        return user_id

    User = Annotated[int, Depends(current_user)]

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never reflect password values from Pydantic's default 'input' error field.
        return JSONResponse({'detail': [{'loc': e['loc'], 'msg': e['msg']} for e in exc.errors()]}, status_code=422)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        return JSONResponse({'detail': 'Banco temporariamente indisponível. Tente novamente.'}, status_code=503)

    @app.get('/api/saude')
    def health():
        with db.connection() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
        return {'status': 'ok', 'versao': '0.3.0', 'banco': 'SQLite', 'schema': version, 'build': app.state.runtime.get('build', 'dev'), 'instalado': app.state.runtime.get('instalado', False)}

    @app.get('/api/perfis')
    def profiles():
        with db.connection() as conn:
            return [dict(r) for r in conn.execute('SELECT id,nome,avatar_id FROM usuarios ORDER BY nome_chave')]

    @app.post('/api/perfis', status_code=201)
    def create_profile(model: ProfileCreate):
        encoded = encode_password(model.senha)
        try:
            with db.connection() as conn:
                cursor = conn.execute('INSERT INTO usuarios(nome,nome_chave,senha_hash) VALUES(?,?,?)', (model.nome, normalize(model.nome), encoded))
                return {'id': cursor.lastrowid, 'nome': model.nome, 'avatar_id': None}
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, 'Já existe um perfil com esse nome.') from exc

    @app.post('/api/sessao')
    def login(model: Login):
        # Lock makes login atomic with password change/session revocation.
        with sessions.lock:
            if not sessions.allow_attempt(model.perfil_id):
                raise HTTPException(429, 'Muitas tentativas. Aguarde um minuto.', headers={'Retry-After': '60'})
            with db.connection() as conn:
                profile = conn.execute('SELECT * FROM usuarios WHERE id=?', (model.perfil_id,)).fetchone()
            if not profile or not check_password(model.senha, profile['senha_hash']):
                raise HTTPException(401, 'Perfil ou senha incorretos.')
            sessions.clear_attempts(model.perfil_id)
            result = {'token': sessions.create(profile['id']), 'expira_em_segundos': 43200, 'perfil': {k: profile[k] for k in ('id', 'nome', 'avatar_id')}, 'aparelho_token': None, 'aparelho_id': None}
            if model.lembrar:
                with db.connection() as conn:
                    device = remember_device(conn, profile['id'], model.aparelho.strip() or 'Aparelho sem nome')
                result.update({'aparelho_token': device['token'], 'aparelho_id': device['id']})
            return result

    @app.post('/api/sessao/aparelho')
    def login_with_device(model: DeviceToken, request: Request):
        # "Lembrar neste aparelho": a credencial é trocada a cada uso, então uma cópia antiga para de valer.
        if not device_throttle.allow(hash(request.client.host if request.client else '')):
            raise HTTPException(429, 'Muitas tentativas. Aguarde um minuto.', headers={'Retry-After': '60'})
        with sessions.lock, db.connection() as conn:
            device = device_login(conn, model.token)
            if not device:
                raise HTTPException(401, 'Este aparelho não está mais lembrado. Entre com a senha.')
            profile = conn.execute('SELECT id,nome,avatar_id FROM usuarios WHERE id=?', (device['user_id'],)).fetchone()
            if not profile:
                raise HTTPException(401, 'Perfil não encontrado.')
            return {'token': sessions.create(profile['id']), 'expira_em_segundos': 43200, 'perfil': dict(profile), 'aparelho_token': device['token'], 'aparelho_id': device['id']}

    @app.get('/api/conta/aparelhos')
    def devices(user_id: User):
        with db.connection() as conn:
            return list_devices(conn, user_id)

    @app.delete('/api/conta/aparelhos/{device_id}', status_code=204)
    def forget_one_device(device_id: int, user_id: User):
        with db.connection() as conn:
            if not forget_device(conn, user_id, device_id):
                raise HTTPException(404, 'Aparelho não encontrado.')

    @app.delete('/api/conta/aparelhos', status_code=204)
    def forget_every_device(user_id: User):
        with db.connection() as conn:
            forget_devices(conn, user_id)

    @app.delete('/api/sessao', status_code=204)
    def logout(user_id: User, credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]):
        sessions.revoke(credentials.credentials)

    @app.get('/api/conta')
    def account(user_id: User):
        with db.connection() as conn:
            return dict(conn.execute('SELECT id,nome,avatar_id FROM usuarios WHERE id=?', (user_id,)).fetchone())

    @app.put('/api/conta/senha', status_code=204)
    def change_password(model: PasswordChange, user_id: User):
        with sessions.lock:
            if not sessions.allow_attempt(user_id):
                raise HTTPException(429, 'Muitas tentativas. Aguarde um minuto.')
            with db.connection() as conn:
                row = conn.execute('SELECT senha_hash FROM usuarios WHERE id=?', (user_id,)).fetchone()
                if not check_password(model.senha_atual, row['senha_hash']):
                    raise HTTPException(401, 'Senha atual incorreta.')
                conn.execute('UPDATE usuarios SET senha_hash=? WHERE id=?', (encode_password(model.nova_senha), user_id))
                forget_devices(conn, user_id)  # Trocar a senha desconecta todos os aparelhos lembrados.
            sessions.revoke_user(user_id)
            sessions.clear_attempts(user_id)

    @app.put('/api/perfis/{profile_id}/redefinir-senha', status_code=204)
    def reset_password(profile_id: int, model: PasswordReset, request: Request):
        # "Esqueci a senha": só deste computador. Quem está no PC já tem acesso aos arquivos da biblioteca; pelo celular ou
        # pela rede a redefinição é recusada. Todas as sessões e aparelhos lembrados do perfil são desconectados e o evento
        # fica no registro do aplicativo.
        if not from_this_computer(request):
            raise HTTPException(403, 'A senha só pode ser redefinida neste computador, não pelo celular ou pela rede.')
        if not reset_throttle.allow(profile_id):
            raise HTTPException(429, 'Muitas redefinições seguidas. Aguarde alguns minutos.', headers={'Retry-After': '300'})
        with sessions.lock:
            with db.connection() as conn:
                profile = conn.execute('SELECT id,nome FROM usuarios WHERE id=?', (profile_id,)).fetchone()
                if not profile:
                    raise HTTPException(404, 'Perfil não encontrado.')
                conn.execute('UPDATE usuarios SET senha_hash=? WHERE id=?', (encode_password(model.nova_senha), profile_id))
                forget_devices(conn, profile_id)
            sessions.revoke_user(profile_id)
            sessions.clear_attempts(profile_id)
        logging.getLogger('nexus.conta').warning('Senha do perfil "%s" redefinida neste computador.', profile['nome'])

    @app.put('/api/conta/avatar')
    def avatar(model: ImageRef, user_id: User):
        with db.connection() as conn:
            validate_image(conn, model.imagem_id, user_id, 'avatar')
            conn.execute('UPDATE usuarios SET avatar_id=? WHERE id=?', (model.imagem_id, user_id))
        return {'avatar_id': model.imagem_id}

    def from_this_computer(request: Request) -> bool:
        return request.client is not None and request.client.host in LOOPBACK

    @app.get('/api/acesso-rede')
    def network_status(request: Request, user_id: User):
        return {**network.status(), 'local': from_this_computer(request)}

    @app.put('/api/acesso-rede')
    def network_update(model: NetworkInput, request: Request, user_id: User):
        # Only the computer that owns the library may expose it; a phone cannot widen its own access.
        if not from_this_computer(request):
            raise HTTPException(403, 'O acesso pelo celular só pode ser alterado neste computador.')
        try:
            if model.ativo:
                network.enable(model.porta or network.settings['porta'])
            else:
                network.disable()
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {**network.status(), 'local': True}

    @app.get('/api/acesso-rede/ca.crt')
    def network_authority():
        # Public certificate only; the private key never leaves the data directory.
        path = network.certificates.ca_cert
        if not path.is_file():
            raise HTTPException(404, 'O certificado ainda não foi gerado. Ligue o acesso pelo celular no computador.')
        return FileResponse(path, media_type='application/x-x509-ca-cert', filename='nexus-ca.crt')

    @app.get('/api/resumo')
    def summary(user_id: User):
        with db.connection() as conn:
            row = conn.execute('SELECT count(*) total, coalesce(sum(progresso>0 AND progresso<100),0) em_andamento, coalesce(sum(progresso=100),0) concluidos, coalesce(sum(favorito),0) favoritos FROM jogos WHERE usuario_id=?', (user_id,)).fetchone()
            collections = conn.execute('SELECT count(*) FROM colecoes WHERE usuario_id=?', (user_id,)).fetchone()[0]
        return {**dict(row), 'colecoes': collections}

    @app.get('/api/jogos')
    def games(user_id: User, busca: str = Query('', max_length=150), genero: str = Query('', max_length=80), favorito: bool = False,
              colecao_id: int | None = Query(None, gt=0), limite: int = Query(40, ge=1, le=100), pagina: int = Query(1, ge=1, le=100000)):
        clauses, params = ['usuario_id=?'], [user_id]
        if busca:
            key = normalize(busca).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("nome_chave LIKE ? ESCAPE '\\'")
            params.append('%' + key + '%')
        if genero:
            clauses.append('genero=?')
            params.append(genero)
        if favorito:
            clauses.append('favorito=1')
        if colecao_id is not None:
            clauses.append('colecao_id=?')
            params.append(colecao_id)
        where = ' AND '.join(clauses)
        with db.connection() as conn:
            total = conn.execute('SELECT count(*) FROM jogos WHERE ' + where, params).fetchone()[0]
            rows = conn.execute(f'SELECT {SUMMARY_COLUMNS} FROM jogos WHERE {where} ORDER BY ordem,nome_chave,id LIMIT ? OFFSET ?', (*params, limite, (pagina - 1) * limite))
            return {'itens': [game_result(row) for row in rows], 'total': total, 'pagina': pagina, 'limite': limite}

    @app.get('/api/destaques')
    def highlights(user_id: User):
        with db.connection() as conn:
            return [game_result(row) for row in conn.execute(f"SELECT {SUMMARY_COLUMNS} FROM jogos WHERE usuario_id=? AND progresso>0 AND progresso<100 AND status_avancado NOT IN ('Concluído','Abandonado','Pausado','Na fila') ORDER BY progresso DESC,nome_chave,id LIMIT 20", (user_id,))]

    @app.post('/api/jogos', status_code=201)
    def create_game(model: GameInput, user_id: User):
        with db.connection() as conn:
            return save_game(conn, model, user_id)

    @app.get('/api/jogos/{game_id}')
    def game(game_id: int, user_id: User):
        with db.connection() as conn:
            return game_result(owned(conn, 'jogos', game_id, user_id))

    @app.patch('/api/jogos/{game_id}')
    def patch_game(game_id: int, patch: dict, user_id: User):
        unknown = set(patch) - set(GameInput.model_fields)
        if unknown:
            raise HTTPException(422, 'Campos de jogo desconhecidos.')
        with db.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            previous = game_result(owned(conn, 'jogos', game_id, user_id))
            previous = {k: v for k, v in previous.items() if k in GameInput.model_fields}
            try:
                model = GameInput.model_validate({**previous, **patch})
            except ValidationError as exc:
                raise HTTPException(422, [{'loc': e['loc'], 'msg': e['msg']} for e in exc.errors()]) from exc
            return save_game(conn, model, user_id, game_id)

    @app.delete('/api/jogos/{game_id}', status_code=204)
    def delete_game(game_id: int, user_id: User):
        with db.connection() as conn:
            owned(conn, 'jogos', game_id, user_id)
            conn.execute('DELETE FROM jogos WHERE id=? AND usuario_id=?', (game_id, user_id))

    @app.get('/api/colecoes')
    def collections(user_id: User):
        with db.connection() as conn:
            rows = conn.execute('SELECT c.id,c.nome,c.capa_id,count(j.id) total FROM colecoes c LEFT JOIN jogos j ON j.colecao_id=c.id AND j.usuario_id=c.usuario_id WHERE c.usuario_id=? GROUP BY c.id ORDER BY c.nome_chave', (user_id,)).fetchall()
            result = []
            for row in rows:
                covers = conn.execute('SELECT capa_id FROM jogos WHERE usuario_id=? AND colecao_id=? AND capa_id IS NOT NULL ORDER BY ordem,nome_chave,id LIMIT 4', (user_id, row['id']))
                result.append({**dict(row), 'mosaico': [r['capa_id'] for r in covers]})
            return result

    @app.post('/api/colecoes', status_code=201)
    def create_collection(model: CollectionInput, user_id: User):
        with db.connection() as conn:
            return save_collection(conn, model, user_id)

    @app.put('/api/colecoes/{collection_id}')
    def update_collection(collection_id: int, model: CollectionInput, user_id: User):
        with db.connection() as conn:
            return save_collection(conn, model, user_id, collection_id)

    @app.delete('/api/colecoes/{collection_id}', status_code=204)
    def delete_collection(collection_id: int, user_id: User):
        with db.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            owned(conn, 'colecoes', collection_id, user_id)
            conn.execute("UPDATE jogos SET colecao_id=NULL,grupo='' WHERE colecao_id=? AND usuario_id=?", (collection_id, user_id))
            conn.execute('DELETE FROM colecoes WHERE id=? AND usuario_id=?', (collection_id, user_id))

    def process_image(user_id, kind, data, crop):
        try:
            with db.connection() as conn:
                return store_image(conn, db.directory, user_id, kind, data, crop)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post('/api/imagens', status_code=201)
    async def upload(request: Request, user_id: User, tipo: Literal['capa', 'avatar', 'colecao'] = 'capa',
                     x: int | None = Query(None, ge=0), y: int | None = Query(None, ge=0),
                     largura: int | None = Query(None, gt=0), altura: int | None = Query(None, gt=0)):
        values = [x, y, largura, altura]
        if any(v is not None for v in values) and not all(v is not None for v in values):
            raise HTTPException(422, 'Informe x, y, largura e altura para recortar.')
        crop = Crop(x=x, y=y, width=largura, height=altura) if x is not None else None
        data = await request.body()
        return await run_in_threadpool(process_image, user_id, tipo, data, crop)

    # Manutenção: backup, restauração, integridade e órfãs abrangem todos os perfis, então só o computador pode pedir.
    def this_computer_only(request: Request):
        if not from_this_computer(request):
            raise HTTPException(403, 'Backup e manutenção só podem ser feitos neste computador.')

    def maintenance_call(action, *args):
        if not maintenance.MAINTENANCE.acquire(timeout=1):
            raise HTTPException(409, 'Outra operação de manutenção está em andamento.')
        try:
            return action(*args)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            maintenance.MAINTENANCE.release()

    @app.get('/api/manutencao/backups')
    def backups(request: Request, user_id: User):
        this_computer_only(request)
        return {'pasta': str(maintenance.backups_directory(db)), 'itens': maintenance.list_backups(db)}

    @app.post('/api/manutencao/backups', status_code=201)
    def make_backup(request: Request, user_id: User):
        this_computer_only(request)
        return maintenance_call(maintenance.create_backup, db)

    @app.get('/api/manutencao/backups/{nome}')
    def download_backup(nome: str, request: Request, user_id: User):
        this_computer_only(request)
        try:
            path = maintenance.backup_path(db, nome)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, 'Backup não encontrado.') from exc
        return FileResponse(path, media_type='application/zip', filename=nome)

    @app.delete('/api/manutencao/backups/{nome}', status_code=204)
    def remove_backup(nome: str, request: Request, user_id: User):
        this_computer_only(request)
        maintenance_call(maintenance.delete_backup, db, nome)

    @app.post('/api/manutencao/backups/{nome}/restaurar')
    def restore(nome: str, request: Request, user_id: User):
        this_computer_only(request)
        result = maintenance_call(maintenance.restore_backup, db, nome)
        sessions.revoke_all()  # os perfis e senhas agora são os do backup
        return result

    @app.get('/api/manutencao/integridade')
    def integrity_check(request: Request, user_id: User):
        this_computer_only(request)
        return maintenance.integrity(db)

    @app.get('/api/manutencao/orfas')
    def orphans(request: Request, user_id: User):
        this_computer_only(request)
        return maintenance.find_orphans(db)

    @app.post('/api/manutencao/orfas/limpar')
    def clean_orphans(request: Request, user_id: User):
        this_computer_only(request)
        return maintenance_call(maintenance.clean_orphans, db)

    # Atualização do aplicativo instalado: verificar, preparar (hash + autoteste), aplicar com confirmação, reverter.
    def updater_or_404():
        updater = app.state.updater
        if updater is None:
            raise HTTPException(404, 'Atualizações automáticas só existem no aplicativo instalado. No modo portátil, recompile e use Abrir Nexus.bat.')
        return updater

    def update_call(action):
        try:
            return action()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(409, f'Falha na atualização: {exc}') from exc

    def schedule_shutdown():
        shutdown = app.state.shutdown
        if shutdown:
            threading.Timer(1.5, shutdown).start()

    @app.get('/api/atualizacao')
    def update_status(request: Request, user_id: User):
        this_computer_only(request)
        base = {**app.state.runtime, 'instalado': app.state.runtime.get('instalado', False)}
        updater = app.state.updater
        return {**base, **(updater.status() if updater else {'canal': '', 'canal_configurado': False, 'disponivel': None, 'preparada': None, 'anterior': None, 'erro': ''})}

    @app.post('/api/atualizacao/verificar')
    def update_check(request: Request, user_id: User):
        this_computer_only(request)
        updater = updater_or_404()
        return update_call(updater.check)

    @app.post('/api/atualizacao/preparar')
    def update_prepare(request: Request, user_id: User):
        this_computer_only(request)
        updater = updater_or_404()
        return update_call(updater.prepare)

    @app.post('/api/atualizacao/aplicar')
    def update_apply(request: Request, user_id: User):
        this_computer_only(request)
        updater = updater_or_404()
        result = update_call(updater.apply)
        schedule_shutdown()
        return {'aplicando': result['aplicando'], 'fechando': app.state.shutdown is not None}

    @app.post('/api/atualizacao/reverter')
    def update_rollback(request: Request, user_id: User):
        this_computer_only(request)
        updater = updater_or_404()
        update_call(updater.rollback)
        schedule_shutdown()
        return {'revertendo': True, 'fechando': app.state.shutdown is not None}

    @app.get('/api/capas/busca')
    def cover_search(user_id: User, nome: str = Query(..., min_length=2, max_length=120), fonte: Literal['todas', 'steam', 'wikipedia'] = 'todas'):
        # Fontes públicas sem chave; cada candidato traz um identificador estável para buscar a ficha depois.
        if not cover_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas buscas seguidas. Aguarde um minuto.', headers={'Retry-After': '60'})
        sources = tuple(SOURCES) if fonte == 'todas' else (fonte,)
        return search_covers(nome.strip(), sources, cache=search_cache)

    def external_details(source: str, external_id: str) -> dict:
        try:
            return game_details(source, external_id, cache=details_cache)
        except (ValueError, OSError, http.client.HTTPException) as exc:
            raise HTTPException(404, f'Não foi possível obter os detalhes deste jogo na fonte ({exc}).') from exc

    @app.get('/api/capas/detalhes')
    def cover_details(user_id: User, fonte: Literal['steam', 'wikipedia'], id: str = Query(..., min_length=1, max_length=64, pattern=r'^[A-Za-z0-9:_-]+$'), jogo_id: int | None = Query(None, gt=0)):
        if not details_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas consultas seguidas. Aguarde um minuto.', headers={'Retry-After': '60'})
        details = external_details(fonte, id)
        with db.connection() as conn:
            return {'detalhes': details, 'duplicado_em': find_duplicate(conn, user_id, fonte, id, jogo_id)}

    @app.post('/api/capas/aplicar', status_code=201)
    def cover_apply(model: CandidateRef, user_id: User):
        """Escolha de um resultado: a ficha e a capa vêm do mesmo identificador; a URL da imagem é montada pelo serviço.

        Nada é gravado no jogo aqui: a interface preenche o formulário e só persiste em "Salvar jogo".
        """
        if not details_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas consultas seguidas. Aguarde um minuto.', headers={'Retry-After': '60'})
        details = external_details(model.fonte, model.id)
        image, image_error = None, ''
        if details.get('imagem'):
            try:
                image = process_image(user_id, 'capa', download_cover(details), None)
            except (ValueError, OSError, http.client.HTTPException, HTTPException) as exc:
                image_error = 'A capa desta fonte não pôde ser baixada; os dados foram preenchidos mesmo assim.'
                if isinstance(exc, HTTPException) and exc.status_code >= 500:
                    raise
        else:
            image_error = 'Esta fonte não tem capa para o jogo; escolha outra capa, um arquivo ou um link.'
        with db.connection() as conn:
            duplicate = find_duplicate(conn, user_id, model.fonte, model.id, model.jogo_id)
        return {'detalhes': details, 'imagem': image, 'erro_capa': image_error, 'duplicado_em': duplicate}

    @app.get('/api/capas/previa')
    def cover_preview(user_id: User, url: str = Query(..., min_length=12, max_length=2048)):
        # Only the image hosts of the built-in sources; everything else is refused before any connection.
        if not image_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas prévias seguidas. Aguarde um minuto.', headers={'Retry-After': '60'})
        try:
            content_type, data = fetch_preview(url)
        except (ValueError, OSError, http.client.HTTPException) as exc:
            raise HTTPException(404, 'Prévia indisponível.') from exc
        return Response(content=data, media_type=content_type)

    @app.post('/api/imagens/url', status_code=201)
    def upload_url(model: RemoteImage, user_id: User):
        if not image_throttle.allow(user_id):
            raise HTTPException(429, 'Muitos downloads seguidos. Aguarde um minuto.', headers={'Retry-After': '60'})
        try:
            data = download_image(model.url)
        except (ValueError, OSError, http.client.HTTPException) as exc:
            raise HTTPException(422, 'Não foi possível baixar a imagem. Use um link direto HTTPS público para JPEG, PNG ou WebP.') from exc
        return process_image(user_id, model.tipo, data, model.recorte)

    @app.get('/api/imagens/{image_id}')
    def image(image_id: str, user_id: User, miniatura: bool = False):
        with db.connection() as conn:
            owned(conn, 'imagens', image_id, user_id)
        path = db.directory / 'images' / f'{image_id}{".thumb" if miniatura else ""}.webp'
        if not path.is_file():
            raise HTTPException(404, 'Imagem ausente do armazenamento.')
        return FileResponse(path, media_type='image/webp')

    @app.get('/api/perfis/{profile_id}/avatar')
    def public_avatar(profile_id: int):
        # Only the selected thumbnail is public, for the local profile chooser.
        with db.connection() as conn:
            profile = conn.execute('SELECT avatar_id FROM usuarios WHERE id=?', (profile_id,)).fetchone()
        if not profile or not profile['avatar_id']:
            raise HTTPException(404, 'Perfil sem avatar.')
        path = db.directory / 'images' / f'{profile["avatar_id"]}.thumb.webp'
        if not path.is_file():
            raise HTTPException(404, 'Avatar ausente do armazenamento.')
        return FileResponse(path, media_type='image/webp')

    return app
