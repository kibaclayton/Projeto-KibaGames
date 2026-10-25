import json
import sqlite3
from fastapi import HTTPException
from .database import normalize
from .models import GameInput

SUMMARY_COLUMNS = 'id,nome,plataforma,progresso,capa_id,data_inicio,data_termino,ordem,favorito,colecao_id,trofeus_obtidos,trofeus_total,status_avancado,genero,minutos_jogados,data_lancamento,desenvolvedor,publicadora,fonte_externa,id_externo,atualizado'


def owned(conn, table, row_id, user_id):
    if table not in ('jogos', 'colecoes', 'imagens'):
        raise ValueError('Tabela inválida.')
    row = conn.execute(f'SELECT * FROM {table} WHERE id=? AND usuario_id=?', (row_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Registro não encontrado.')
    return row


def validate_image(conn, image_id, user_id, kind):
    if image_id:
        image = owned(conn, 'imagens', image_id, user_id)
        if image['tipo'] != kind:
            raise HTTPException(422, 'A imagem não corresponde a esse tipo de uso.')


def game_result(row):
    data = dict(row)
    data.pop('usuario_id', None)
    data.pop('nome_chave', None)
    data['favorito'] = bool(data['favorito'])
    total, earned = data['trofeus_total'], data['trofeus_obtidos']
    data['trofeus_percentual'] = round(earned * 100 / total, 2) if total else 0
    data['platinado'] = total > 0 and earned == total
    if 'cronograma' in data:
        data['cronograma'] = json.loads(data['cronograma'])
    return data


def game_values(model: GameInput):
    data = model.model_dump(mode='json')
    data['nome_chave'] = normalize(data['nome'])
    data['cronograma'] = json.dumps(data['cronograma'], sort_keys=True, ensure_ascii=False)
    return data


def save_game(conn, model: GameInput, user_id: int, game_id: int | None = None):
    validate_image(conn, model.capa_id, user_id, 'capa')
    if model.colecao_id:
        owned(conn, 'colecoes', model.colecao_id, user_id)
    values = game_values(model)
    if game_id is None:
        values['usuario_id'] = user_id
        cursor = conn.execute(f"INSERT INTO jogos({','.join(values)}) VALUES({','.join('?' for _ in values)})", tuple(values.values()))
        game_id = cursor.lastrowid
    else:
        owned(conn, 'jogos', game_id, user_id)
        conn.execute(f"UPDATE jogos SET {','.join(key + '=?' for key in values)}, atualizado=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND usuario_id=?", (*values.values(), game_id, user_id))
    return game_result(owned(conn, 'jogos', game_id, user_id))


def find_duplicate(conn, user_id: int, source: str, external_id: str, exclude_game: int | None = None):
    """Outro jogo do mesmo perfil já ligado a este resultado externo; aviso, não bloqueio (edições diferentes existem)."""
    if not source or not external_id:
        return None
    row = conn.execute('SELECT id,nome,plataforma FROM jogos WHERE usuario_id=? AND fonte_externa=? AND id_externo=? AND id IS NOT ? ORDER BY id LIMIT 1',
                       (user_id, source, external_id, exclude_game)).fetchone()
    return dict(row) if row else None


def save_collection(conn, model, user_id, collection_id=None):
    validate_image(conn, model.capa_id, user_id, 'colecao')
    try:
        if collection_id is None:
            cursor = conn.execute('INSERT INTO colecoes(usuario_id,nome,nome_chave,capa_id) VALUES(?,?,?,?)',
                                  (user_id, model.nome, normalize(model.nome), model.capa_id))
            collection_id = cursor.lastrowid
        else:
            owned(conn, 'colecoes', collection_id, user_id)
            conn.execute('UPDATE colecoes SET nome=?,nome_chave=?,capa_id=? WHERE id=? AND usuario_id=?',
                         (model.nome, normalize(model.nome), model.capa_id, collection_id, user_id))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Já existe uma coleção com esse nome.') from exc
    return {'id': collection_id, 'nome': model.nome, 'capa_id': model.capa_id}
