from contextlib import asynccontextmanager
import http.client
import json
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .database import Database, data_directory, normalize
from .images import MAX_BYTES, download_image, store_image
from .models import CollectionInput, Crop, GameInput, ImageRef, Login, PasswordChange, ProfileCreate, RemoteImage
from .security import Sessions, check_password, encode_password
from .service import SUMMARY_COLUMNS, game_result, owned, save_collection, save_game, validate_image

ORIGINS = ['http://127.0.0.1:1420', 'http://localhost:1420', 'http://127.0.0.1:4173',
           'http://localhost:4173', 'http://127.0.0.1:8765', 'http://localhost:8765',
           'http://tauri.localhost', 'https://tauri.localhost', 'tauri://localhost']


class LocalRequests:
    """Reject foreign browser origins before mutations; bound body memory for all routes."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        origin = headers.get(b'origin', b'').decode('latin1')
        own_origin = 'http://' + headers.get(b'host', b'').decode('latin1')
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
    app.state.db = db
    app.state.sessions = sessions
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET', 'POST', 'PATCH', 'PUT', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])
    app.add_middleware(LocalRequests)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
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
        return {'status': 'ok', 'versao': '0.3.0', 'banco': 'SQLite', 'schema': version}

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
            return {'token': sessions.create(profile['id']), 'expira_em_segundos': 43200, 'perfil': {k: profile[k] for k in ('id', 'nome', 'avatar_id')}}

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
            sessions.revoke_user(user_id)
            sessions.clear_attempts(user_id)

    @app.put('/api/conta/avatar')
    def avatar(model: ImageRef, user_id: User):
        with db.connection() as conn:
            validate_image(conn, model.imagem_id, user_id, 'avatar')
            conn.execute('UPDATE usuarios SET avatar_id=? WHERE id=?', (model.imagem_id, user_id))
        return {'avatar_id': model.imagem_id}

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

    @app.post('/api/imagens/url', status_code=201)
    def upload_url(model: RemoteImage, user_id: User):
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
