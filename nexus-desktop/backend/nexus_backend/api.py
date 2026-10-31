from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
from . import avatars, igdb, maintenance, trophies
from .models import (AvatarSlot, CandidateRef, CollectionInput, Crop, DeviceToken, GameInput, ImageRef, Login, NetworkInput, OrderInput, PasswordChange, PasswordReset,
                     PreferencesInput, ProfileCreate, RemoteImage, TrophyImportInput, TrophySource, TrophySourceInput, TrophySyncInput)
from .network import LOOPBACK, NetworkAccess
from .security import Sessions, check_password, device_login, encode_password, forget_device, forget_devices, list_devices, remember_device
from .service import SUMMARY_COLUMNS, find_duplicate, game_result, owned, reorder_games, save_collection, save_game, validate_image

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
    trophy_throttle = Throttle(limit=20, window=300)  # listas, importações e sincronizações de troféus por perfil
    trophy_view_throttle = Throttle(limit=60, window=300)  # visualizador de conquistas por jogo
    complete_throttle = Throttle(limit=3, window=600)  # capas em lote pela Steam: dezenas de pedidos por execução
    achievements_cache = Cache(60 * 60)  # esquema e raridade global por jogo (nunca o estado do jogador)
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
        # Define a foto ativa. Uma imagem fora da galeria entra na primeira posição livre; com cinco ocupadas, a interface pede qual substituir.
        with db.connection() as conn:
            validate_image(conn, model.imagem_id, user_id, 'avatar')
            if model.imagem_id:
                avatars.ensure_in_gallery(conn, user_id, model.imagem_id)
            conn.execute('UPDATE usuarios SET avatar_id=? WHERE id=?', (model.imagem_id, user_id))
        return {'avatar_id': model.imagem_id}

    @app.get('/api/conta/avatares')
    def avatar_gallery(user_id: User):
        with db.connection() as conn:
            return avatars.gallery(conn, user_id)

    @app.put('/api/conta/avatares/{posicao}')
    def avatar_slot(posicao: int, model: AvatarSlot, user_id: User):
        if not 1 <= posicao <= avatars.SLOTS:
            raise HTTPException(422, 'Posição inválida.')
        with db.connection() as conn:
            validate_image(conn, model.imagem_id, user_id, 'avatar')
            return avatars.set_slot(conn, user_id, posicao, model.imagem_id)

    @app.delete('/api/conta/avatares/{posicao}')
    def avatar_slot_remove(posicao: int, user_id: User):
        with db.connection() as conn:
            return avatars.remove_slot(conn, user_id, posicao)

    @app.get('/api/avatares/busca')
    def avatar_search(user_id: User, termo: str = Query(..., min_length=2, max_length=80)):
        if not cover_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas buscas seguidas. Aguarde um minuto.', headers={'Retry-After': '60'})
        try:
            return {'itens': avatars.search_commons(termo.strip())}
        except (ValueError, OSError, http.client.HTTPException) as exc:
            raise HTTPException(503, f'Busca de imagens indisponível no momento ({exc}).') from exc

    @app.get('/api/conta/preferencias')
    def preferences(user_id: User):
        with db.connection() as conn:
            row = conn.execute('SELECT preferencias FROM usuarios WHERE id=?', (user_id,)).fetchone()
        try:
            stored = json.loads(row['preferencias'] or '{}')
        except ValueError:
            stored = {}
        return PreferencesInput.model_validate({k: v for k, v in stored.items() if k in PreferencesInput.model_fields}).model_dump()

    @app.put('/api/conta/preferencias')
    def save_preferences(model: PreferencesInput, user_id: User):
        with db.connection() as conn:
            conn.execute('UPDATE usuarios SET preferencias=? WHERE id=?', (json.dumps(model.model_dump(), ensure_ascii=False), user_id))
        return model.model_dump()

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
              colecao_id: int | None = Query(None, gt=0), limite: int = Query(40, ge=1, le=100), pagina: int = Query(1, ge=1, le=100000),
              ordenacao: Literal['minha', 'nome', 'recentes', 'progresso', 'colecao'] = 'minha'):
        # 'minha' = ordem manual da biblioteca (posicao); 'colecao' = sequência dentro da coleção (ordem), usada ao abrir uma pasta.
        orders = {'minha': 'posicao,id', 'nome': 'nome_chave,id', 'recentes': 'atualizado DESC,id DESC', 'progresso': 'progresso DESC,nome_chave,id', 'colecao': 'ordem,nome_chave,id'}
        order_by = orders[ordenacao]
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
            rows = conn.execute(f'SELECT {SUMMARY_COLUMNS} FROM jogos WHERE {where} ORDER BY {order_by} LIMIT ? OFFSET ?', (*params, limite, (pagina - 1) * limite))
            return {'itens': [game_result(row) for row in rows], 'total': total, 'pagina': pagina, 'limite': limite}

    @app.get('/api/destaques')
    def highlights(user_id: User):
        with db.connection() as conn:
            return [game_result(row) for row in conn.execute(f"SELECT {SUMMARY_COLUMNS} FROM jogos WHERE usuario_id=? AND progresso>0 AND progresso<100 AND status_avancado NOT IN ('Concluído','Abandonado','Pausado','Na fila') ORDER BY progresso DESC,nome_chave,id LIMIT 20", (user_id,))]

    @app.put('/api/jogos/ordem')
    def order_games(model: OrderInput, user_id: User):
        """Ordem manual da biblioteca: atômica e limitada ao perfil autenticado; a sequência das coleções (`ordem`) não muda."""
        with db.connection() as conn:
            return {'total': reorder_games(conn, user_id, model.ids)}

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
    def cover_search(user_id: User, nome: str = Query(..., min_length=2, max_length=120), fonte: Literal['todas', 'steam', 'wikipedia', 'igdb'] = 'todas',
                     plataforma: Literal['todas', 'pc', 'playstation', 'xbox', 'nintendo'] = 'todas'):
        # Fontes públicas sem chave (Steam, Wikipedia/Wikidata) e IGDB opcional com chave local; cada candidato traz um id estável.
        if not cover_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas buscas seguidas. Aguarde um minuto.', headers={'Retry-After': '60'})
        sources = tuple(SOURCES) if fonte == 'todas' else (fonte,)
        result = search_covers(nome.strip(), sources, cache=search_cache, family=plataforma, igdb_config=igdb.load_config(db.directory))
        return {**result, 'igdb_configurada': igdb.configured(db.directory)}

    @app.get('/api/capas/fontes')
    def cover_sources(user_id: User):
        return {'igdb_configurada': igdb.configured(db.directory), 'arquivo_igdb': str(igdb.config_path(db.directory))}

    def external_details(source: str, external_id: str) -> dict:
        try:
            return game_details(source, external_id, cache=details_cache, igdb_config=igdb.load_config(db.directory))
        except (ValueError, OSError, http.client.HTTPException) as exc:
            raise HTTPException(404, f'Não foi possível obter os detalhes deste jogo na fonte ({exc}).') from exc

    @app.get('/api/capas/detalhes')
    def cover_details(user_id: User, fonte: Literal['steam', 'wikipedia', 'igdb'], id: str = Query(..., min_length=1, max_length=64, pattern=r'^[A-Za-z0-9:_-]+$'), jogo_id: int | None = Query(None, gt=0)):
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

    @app.post('/api/capas/completar')
    def cover_complete(user_id: User):
        """Capas em lote pela Steam para os jogos sem capa e sem fonte: só quando o nome bate exatamente com um resultado.

        Além da capa, o jogo fica ligado ao appid (fonte/id/origem) e os campos de ficha vazios são preenchidos; progresso,
        notas, datas, troféus obtidos e o que já estava preenchido não mudam. Nomes sem correspondência exata voltam na lista
        "escolha no editor", nunca recebem uma capa por palpite. Até 40 jogos por chamada.
        """
        if not complete_throttle.allow(user_id):
            raise HTTPException(429, 'A busca em lote já rodou há pouco. Aguarde alguns minutos.', headers={'Retry-After': '600'})
        with db.connection() as conn:
            rows = [dict(row) for row in conn.execute("SELECT id,nome FROM jogos WHERE usuario_id=? AND capa_id IS NULL AND fonte_externa='' ORDER BY posicao,id LIMIT 41", (user_id,))]
        pending_more = len(rows) > 40
        done, unmatched, failed = [], [], []
        for row in rows[:40]:
            wanted = normalize(row['nome'])
            try:
                candidates = search_covers(row['nome'], ('steam',), cache=search_cache, family='pc')['itens']
            except (ValueError, OSError, http.client.HTTPException):
                failed.append({'id': row['id'], 'nome': row['nome'], 'motivo': 'A Steam não respondeu à busca.'})
                continue
            exact = [item for item in candidates if normalize(item['titulo']) == wanted]
            if len(exact) != 1:
                unmatched.append({'id': row['id'], 'nome': row['nome'], 'motivo': 'Nenhum resultado com o nome exato.' if not exact else 'Mais de um resultado com o mesmo nome.'})
                continue
            try:
                details = external_details('steam', exact[0]['id'])
                image = process_image(user_id, 'capa', download_cover(details), None)
            except (HTTPException, ValueError, OSError, http.client.HTTPException) as exc:
                if isinstance(exc, HTTPException) and exc.status_code >= 500:
                    raise
                logging.getLogger('nexus.capas').warning('Capa em lote de "%s" (appid %s) falhou: %s', row['nome'], exact[0]['id'], exc.detail if isinstance(exc, HTTPException) else exc)
                failed.append({'id': row['id'], 'nome': row['nome'], 'motivo': 'A Steam não forneceu a capa deste jogo.'})
                continue
            with db.connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                previous = game_result(owned(conn, 'jogos', row['id'], user_id))
                current = {k: v for k, v in previous.items() if k in GameInput.model_fields}
                changes = {'capa_id': image['id'], 'fonte_externa': 'steam', 'id_externo': exact[0]['id'], 'url_origem': details['origem']}
                for field, value in (('genero', details['genero']), ('data_lancamento', details['data_lancamento']), ('desenvolvedor', ', '.join(details['desenvolvedores'])[:200]),
                                     ('publicadora', ', '.join(details['publicadoras'])[:200]), ('descricao', details['descricao'])):
                    if value and not current.get(field):
                        changes[field] = value
                if details.get('trofeus_total') and not current['trofeus_total']:
                    changes.update(trofeus_total=details['trofeus_total'], trofeus_fonte=details['trofeus_fonte'], trofeus_escopo=details['trofeus_escopo'], trofeus_consultado_em=details['trofeus_consultado_em'])
                sheet = dict(current.get('ficha') or {})
                for key, value in (details.get('ficha') or {}).items():
                    if value not in (None, '', []) and sheet.get(key) in (None, '', []):
                        sheet[key] = value
                changes['ficha'] = sheet
                try:
                    model = GameInput.model_validate({**current, **changes})
                except ValidationError:
                    failed.append({'id': row['id'], 'nome': row['nome'], 'motivo': 'A ficha da Steam não passou na validação do Nexus.'})
                    continue
                save_game(conn, model, user_id, row['id'])
            done.append({'id': row['id'], 'nome': row['nome'], 'titulo_steam': exact[0]['titulo']})
        return {'atualizados': done, 'sem_correspondencia': unmatched, 'falhas': failed, 'restantes': pending_more}

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

    # Troféus por fontes oficiais (Steam Web API e RetroAchievements), com chave pessoal guardada só neste computador.

    def trophy_config_or_409(source: str, user_id: int) -> dict:
        config = trophies.load_config(db.directory, source, user_id)
        if not config:
            raise HTTPException(409, f'{trophies.LABELS[source]} não está vinculada a este perfil. Vincule em Conta e preferências.')
        return config

    def trophy_allow(user_id: int):
        if not trophy_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas consultas de troféus seguidas. Aguarde alguns minutos.', headers={'Retry-After': '300'})

    @app.get('/api/trofeus/fontes')
    def trophy_sources(request: Request, user_id: User):
        return {'fontes': trophies.all_status(db.directory, user_id), 'local': from_this_computer(request)}

    @app.put('/api/trofeus/fontes/{fonte}')
    def trophy_link(fonte: TrophySource, model: TrophySourceInput, request: Request, user_id: User):
        """Guarda a chave e a identificação em arquivo local depois de uma consulta de teste; a chave nunca volta ao navegador."""
        if not from_this_computer(request):
            raise HTTPException(403, 'Fontes de troféus só podem ser vinculadas neste computador, não pelo celular ou pela rede.')
        trophy_allow(user_id)
        try:
            config = trophies.validate(fonte, model.api_key, model.identificacao)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        warning = ''
        try:
            trophies.list_games(fonte, config, 'recentes')
        except trophies.SourceError as exc:
            if exc.codigo == 'credenciais':
                raise HTTPException(422, str(exc)) from exc
            warning = str(exc)
        trophies.save_config(db.directory, fonte, user_id, config)
        return {**trophies.status(db.directory, fonte, user_id), 'aviso': warning}

    @app.delete('/api/trofeus/fontes/{fonte}', status_code=204)
    def trophy_unlink(fonte: TrophySource, request: Request, user_id: User):
        if not from_this_computer(request):
            raise HTTPException(403, 'Fontes de troféus só podem ser desvinculadas neste computador.')
        trophies.remove_config(db.directory, fonte, user_id)

    @app.get('/api/trofeus/{fonte}/jogos')
    def trophy_games(fonte: TrophySource, user_id: User, modo: Literal['recentes', 'possuidos', 'todos'] = 'recentes'):
        """Jogos da conta vinculada, com a indicação dos que já estão na biblioteca deste perfil."""
        config = trophy_config_or_409(fonte, user_id)
        trophy_allow(user_id)
        try:
            items = trophies.list_games(fonte, config, modo)
        except trophies.SourceError as exc:
            raise HTTPException(409, str(exc)) from exc
        with db.connection() as conn:
            linked = {row['id_externo']: {'id': row['id'], 'nome': row['nome']} for row in conn.execute('SELECT id,nome,id_externo FROM jogos WHERE usuario_id=? AND fonte_externa=?', (user_id, fonte))}
        return {'modo': modo, 'itens': [{**item, 'na_biblioteca': linked.get(item['id'])} for item in items]}

    @app.post('/api/trofeus/{fonte}/importar', status_code=201)
    def trophy_import(fonte: TrophySource, model: TrophyImportInput, user_id: User):
        """Cria jogos a partir da conta vinculada: ficha e capa da fonte, tempo de jogo e troféus da sua conta.

        Só entram identificadores que a própria fonte listou para a conta; jogos já ligados ao mesmo id são ignorados, nunca
        sobrescritos. Progresso, notas, datas e cronograma ficam vazios para você preencher.
        """
        config = trophy_config_or_409(fonte, user_id)
        trophy_allow(user_id)
        if model.colecao_id:
            with db.connection() as conn:
                owned(conn, 'colecoes', model.colecao_id, user_id)
        try:
            available = {item['id']: item for item in trophies.list_games(fonte, config, model.modo)}
        except trophies.SourceError as exc:
            raise HTTPException(409, str(exc)) from exc
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        imported, skipped = [], []
        for external_id in model.ids:
            item = available.get(external_id)
            if not item:
                skipped.append({'id': external_id, 'nome': '', 'motivo': 'Este jogo não está na lista da sua conta nesta fonte.'})
                continue
            with db.connection() as conn:
                duplicate = find_duplicate(conn, user_id, fonte, external_id)
            if duplicate:
                skipped.append({'id': external_id, 'nome': item['titulo'], 'motivo': f'Já está na biblioteca como "{duplicate["nome"]}".'})
                continue
            details = None
            try:
                details = external_details('steam', external_id) if fonte == 'steam' else trophies.retro_details(config, external_id)
            except (HTTPException, ValueError, OSError, http.client.HTTPException) as exc:
                if isinstance(exc, HTTPException) and exc.status_code >= 500:
                    raise
            image = None
            cover_source = details if details and details.get('imagem') else {'fonte': fonte, 'imagem': item['imagem']}
            try:
                image = process_image(user_id, 'capa', download_cover(cover_source), None)
            except (ValueError, OSError, http.client.HTTPException, HTTPException) as exc:
                if isinstance(exc, HTTPException) and exc.status_code >= 500:
                    raise
            earned = None
            if fonte == 'steam':
                try:
                    earned = trophies.steam_achievements(config, external_id)
                except trophies.SourceError:
                    earned = None
            elif item.get('trofeus_total'):
                earned = {'obtidos': item['trofeus_obtidos'] or 0, 'total': item['trofeus_total'], 'escopo': 'jogo base'}
            data = {'nome': (details or item)['titulo'], 'plataforma': item['plataforma'], 'capa_id': image['id'] if image else None,
                    'fonte_externa': fonte, 'id_externo': external_id, 'url_origem': (details or item)['origem'],
                    'minutos_jogados': item.get('minutos') or 0, 'colecao_id': model.colecao_id}
            if details:
                data.update(genero=details['genero'], data_lancamento=details['data_lancamento'], desenvolvedor=', '.join(details['desenvolvedores'])[:200],
                            publicadora=', '.join(details['publicadoras'])[:200], descricao=details['descricao'])
            if earned:
                data.update(trofeus_obtidos=earned['obtidos'], trofeus_total=earned['total'], trofeus_fonte=fonte, trofeus_escopo=earned['escopo'], trofeus_consultado_em=stamp)
            try:
                game = GameInput.model_validate(data)
            except ValidationError as exc:
                skipped.append({'id': external_id, 'nome': item['titulo'], 'motivo': 'A ficha da fonte não passou na validação do Nexus.'})
                logging.getLogger('nexus.trofeus').warning('Importação de %s %s recusada: %s', fonte, external_id, exc.errors()[0]['msg'] if exc.errors() else exc)
                continue
            with db.connection() as conn:
                saved = save_game(conn, game, user_id)
            imported.append({'id': saved['id'], 'nome': saved['nome'], 'capa': image is not None, 'trofeus': earned is not None})
        return {'importados': imported, 'ignorados': skipped}

    @app.get('/api/trofeus/resumo')
    def trophy_overview(user_id: User):
        """Página Troféus: todos os jogos do perfil com obtidos/total, fonte e platina, mais os totais e as fontes vinculadas."""
        with db.connection() as conn:
            rows = [dict(row) for row in conn.execute(
                'SELECT id,nome,plataforma,capa_id,trofeus_obtidos,trofeus_total,trofeus_fonte,trofeus_consultado_em,fonte_externa,id_externo,favorito '
                'FROM jogos WHERE usuario_id=? ORDER BY (trofeus_total>0 AND trofeus_obtidos=trofeus_total) DESC, '
                'CASE WHEN trofeus_total>0 THEN trofeus_obtidos*1.0/trofeus_total ELSE -1 END DESC, nome LIMIT 2000', (user_id,))]
        items = []
        for row in rows:
            total, earned = row['trofeus_total'], row['trofeus_obtidos']
            items.append({'id': row['id'], 'nome': row['nome'], 'plataforma': row['plataforma'], 'capa_id': row['capa_id'], 'favorito': bool(row['favorito']),
                          'trofeus_obtidos': earned, 'trofeus_total': total, 'percentual': round(earned * 100 / total, 1) if total else 0, 'platinado': total > 0 and earned == total,
                          'trofeus_fonte': row['trofeus_fonte'], 'trofeus_consultado_em': row['trofeus_consultado_em'],
                          'fonte': row['fonte_externa'] if row['fonte_externa'] in trophies.SOURCES and row['id_externo'] else ''})
        linked = [source for source, status_ in trophies.all_status(db.directory, user_id).items() if status_['configurada']]
        return {'itens': items, 'fontes_vinculadas': linked,
                'totais': {'jogos': len(items), 'com_trofeus': sum(1 for i in items if i['trofeus_total']), 'platinados': sum(1 for i in items if i['platinado']),
                           'obtidos': sum(i['trofeus_obtidos'] for i in items), 'total': sum(i['trofeus_total'] for i in items), 'ligados': sum(1 for i in items if i['fonte'])}}

    @app.get('/api/trofeus/jogo/{game_id}')
    def trophy_list(game_id: int, user_id: User):
        """Visualizador: cada conquista do jogo (nome, descrição, ícone, obtida e quando, raridade) pela conta vinculada do perfil.

        A contagem que a fonte devolve é gravada no jogo, como na sincronização; esquema e raridade ficam em cache por uma hora.
        """
        with db.connection() as conn:
            game = game_result(owned(conn, 'jogos', game_id, user_id))
        source = game['fonte_externa']
        if source not in trophies.SOURCES or not game['id_externo']:
            raise HTTPException(409, 'Este jogo não está ligado à Steam nem ao RetroAchievements. No editor, escolha o resultado da Steam, ou importe o jogo pela conta vinculada.')
        config = trophy_config_or_409(source, user_id)
        if not trophy_view_throttle.allow(user_id):
            raise HTTPException(429, 'Muitas consultas de troféus seguidas. Aguarde alguns minutos.', headers={'Retry-After': '300'})
        try:
            result = trophies.achievement_list(source, config, game['id_externo'], cache=achievements_cache)
        except trophies.SourceError as exc:
            raise HTTPException(409, str(exc)) from exc
        with db.connection() as conn:
            stamp = trophies.record_counts(conn, user_id, game_id, source, result['obtidos'], result['total'], result['escopo'])
        return {'jogo': {'id': game['id'], 'nome': game['nome'], 'plataforma': game['plataforma'], 'fonte': source, 'titulo_fonte': result['titulo']},
                'itens': result['itens'], 'obtidos': result['obtidos'], 'total': result['total'], 'consultado_em': stamp}

    @app.post('/api/trofeus/sincronizar')
    def trophy_sync(model: TrophySyncInput, user_id: User):
        """Atualiza obtidos/total dos jogos ligados a fontes vinculadas; falhas são relatadas por jogo e nunca zeram valores."""
        trophy_allow(user_id)
        configs = trophies.all_configs(db.directory, user_id)
        if not configs:
            raise HTTPException(409, 'Nenhuma fonte de troféus vinculada a este perfil. Vincule a Steam ou o RetroAchievements em Conta e preferências.')
        with db.connection() as conn:
            if model.jogo_id:
                owned(conn, 'jogos', model.jogo_id, user_id)
            return trophies.sync(conn, user_id, configs, model.jogo_id)

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
