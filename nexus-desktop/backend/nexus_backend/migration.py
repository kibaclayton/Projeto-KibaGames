"""Copy-only MySQL migration. Never imports app.py and never writes to the source database."""
import argparse
from contextlib import closing
import base64
from datetime import date, datetime
from decimal import Decimal
import getpass
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile

from .database import Database, normalize
from .images import store_image
from .models import GameInput
from .security import LEGACY_HASH
from .service import game_values

TABLES = ('usuarios', 'colecoes', 'jogos')


def encode_value(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'$binary': base64.b64encode(bytes(value)).decode('ascii')}
    if isinstance(value, (datetime, date)):
        return {'$date': value.isoformat()}
    if isinstance(value, Decimal):
        return {'$decimal': str(value)}
    return value


def decode_value(value):
    if isinstance(value, dict) and '$binary' in value:
        return base64.b64decode(value['$binary'])
    if isinstance(value, dict) and '$date' in value:
        return value['$date']
    if isinstance(value, dict) and '$decimal' in value:
        return Decimal(value['$decimal'])
    return value


def write_snapshot(path: Path, records, schemas=None):
    """A recoverable copy retaining every original column and original image bytes."""
    counts = dict.fromkeys(TABLES, 0)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript('CREATE TABLE origem(tabela TEXT NOT NULL, id INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(tabela,id)); CREATE TABLE metadados(chave TEXT PRIMARY KEY, valor TEXT NOT NULL);')
        conn.execute('INSERT INTO metadados VALUES(?,?)', ('esquemas_mysql', json.dumps(schemas or {})))
        for table, row in records:
            if table not in TABLES:
                raise ValueError('Tabela de origem inesperada.')
            payload = {key: encode_value(value) for key, value in row.items()}
            conn.execute('INSERT INTO origem VALUES(?,?,?)', (table, row['id'], json.dumps(payload, ensure_ascii=False)))
            counts[table] += 1
        conn.execute('INSERT INTO metadados VALUES(?,?)', ('contagens', json.dumps(counts)))
    return counts


def snapshot_rows(conn, table):
    for row in conn.execute('SELECT payload FROM origem WHERE tabela=? ORDER BY id', (table,)):
        yield {key: decode_value(value) for key, value in json.loads(row[0]).items()}


def migrate_records(records, destination: Path, schemas=None, owner_for_unassigned=None):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError('O destino já existe. Escolha uma pasta nova para não sobrescrever dados.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=destination.name + '.migrando-', dir=destination.parent))
    try:
        counts = write_snapshot(staging / 'origem-mysql.sqlite3', records, schemas)
        db = Database(staging)
        db.initialize()
        with closing(sqlite3.connect(staging / 'origem-mysql.sqlite3')) as source, db.connection() as conn:
            for user in snapshot_rows(source, 'usuarios'):
                if not LEGACY_HASH.fullmatch(user['senha_hash']):
                    raise ValueError(f'Perfil {user["id"]}: formato de senha desconhecido; migração interrompida.')
                conn.execute('INSERT INTO usuarios(id,nome,nome_chave,senha_hash) VALUES(?,?,?,?)',
                             (user['id'], user['nome'], normalize(user['nome']), user['senha_hash']))
                if user.get('avatar'):
                    image = store_image(conn, staging, user['id'], 'avatar', bytes(user['avatar']))
                    conn.execute('UPDATE usuarios SET avatar_id=? WHERE id=?', (image['id'], user['id']))
            for collection in snapshot_rows(source, 'colecoes'):
                conn.execute('INSERT INTO colecoes(id,usuario_id,nome,nome_chave) VALUES(?,?,?,?)',
                             (collection['id'], collection['usuario_id'], collection['nome'], normalize(collection['nome'])))
            for game in snapshot_rows(source, 'jogos'):
                user_id = game.get('usuario_id') or owner_for_unassigned
                if not user_id or not conn.execute('SELECT id FROM usuarios WHERE id=?', (user_id,)).fetchone():
                    raise ValueError(f'Jogo {game["id"]} sem perfil válido. Informe --owner-for-unassigned com um perfil existente quando apropriado.')
                payload = {k: v for k, v in game.items() if k in GameInput.model_fields}
                payload['notas'] = payload.get('notas') or ''
                schedule = payload.get('cronograma') or {}
                payload['cronograma'] = json.loads(schedule) if isinstance(schedule, (str, bytes)) else schedule
                model = GameInput.model_validate(payload)
                values = game_values(model)
                if game.get('capa'):
                    values['capa_id'] = store_image(conn, staging, user_id, 'capa', bytes(game['capa']))['id']
                if not values.get('colecao_id') and values['grupo'].strip():
                    key = normalize(values['grupo'].strip())
                    collection = conn.execute('SELECT id FROM colecoes WHERE usuario_id=? AND nome_chave=?', (user_id, key)).fetchone()
                    values['colecao_id'] = collection['id'] if collection else conn.execute('INSERT INTO colecoes(usuario_id,nome,nome_chave) VALUES(?,?,?)', (user_id, values['grupo'].strip(), key)).lastrowid
                values.update(id=game['id'], usuario_id=user_id)
                if game.get('atualizado'):
                    values['atualizado'] = str(game['atualizado'])
                conn.execute(f"INSERT INTO jogos({','.join(values)}) VALUES({','.join('?' for _ in values)})", tuple(values.values()))
            imported = {t: conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in TABLES}
            if imported['usuarios'] != counts['usuarios'] or imported['jogos'] != counts['jogos'] or imported['colecoes'] < counts['colecoes']:
                raise ValueError('As contagens não conferem.')
            if conn.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Relacionamentos inválidos no destino.')
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('A integridade do SQLite não foi confirmada.')
            report = {'origem': 'MySQL/biblioteca_gamer', 'originais': counts, 'importados': imported,
                      'imagens_webp': conn.execute('SELECT count(*) FROM imagens').fetchone()[0],
                      'integridade': 'ok', 'mysql_alterado': False,
                      'backup': 'origem-mysql.sqlite3', 'owner_for_unassigned': owner_for_unassigned}
            conn.execute('INSERT INTO migracoes(origem,relatorio) VALUES(?,?)', ('mysql', json.dumps(report)))
        with db.connection() as conn:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        (staging / 'relatorio-migracao.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        # Publish only after every row, original backup, image and integrity check succeeds.
        if destination.exists():
            raise ValueError('O destino foi criado por outro processo. Nada será sobrescrito.')
        if staging.resolve().parent != destination.parent or not staging.name.startswith(destination.name + '.migrando-'):
            raise ValueError('Caminho de publicação inválido.')
        staging.rename(destination)
        return report
    except Exception as exc:
        # Keep the original snapshot for recovery; the requested destination remains absent.
        raise ValueError(f'Migração não concluída. Cópia de trabalho preservada em {staging}. Motivo: {exc}') from exc


def saved_credentials():
    raiz = Path(__file__).resolve().parents[3]
    module_path = next((c for c in (raiz / 'conexao_segura.py', raiz / 'legado' / 'conexao_segura.py') if c.is_file()), raiz / 'legado' / 'conexao_segura.py')
    spec = importlib.util.spec_from_file_location('nexus_legacy_connection', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    credentials = module.load_connection()
    if not credentials:
        raise ValueError('Nenhuma conexão MySQL salva foi encontrada para este usuário Windows.')
    return credentials


def mysql_copy(credentials, destination: Path, owner_for_unassigned=None):
    import mysql.connector
    source = mysql.connector.connect(host='127.0.0.1', port=3306, database='biblioteca_gamer',
                                     user=credentials['user'], password=credentials['password'],
                                     connection_timeout=5, charset='utf8mb4')
    try:
        source.start_transaction(consistent_snapshot=True, isolation_level='REPEATABLE READ', readonly=True)
        schemas = {}
        cursor = source.cursor()
        try:
            for table in TABLES:
                cursor.execute(f'SHOW CREATE TABLE {table}')
                schemas[table] = cursor.fetchone()[1]
        finally:
            cursor.close()

        def records():
            cursor = source.cursor(dictionary=True)
            try:
                for table in TABLES:
                    cursor.execute(f'SELECT * FROM {table} ORDER BY id')
                    for row in cursor:
                        yield table, row
            finally:
                cursor.close()
        return migrate_records(records(), destination, schemas, owner_for_unassigned)
    finally:
        source.rollback()
        source.close()


def main():
    parser = argparse.ArgumentParser(description='Copiar MySQL para uma nova pasta SQLite, preservando a origem.')
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--saved-connection', action='store_true')
    parser.add_argument('--mysql-user', default='root')
    parser.add_argument('--owner-for-unassigned', type=int)
    args = parser.parse_args()
    try:
        credentials = saved_credentials() if args.saved_connection else {'user': args.mysql_user, 'password': getpass.getpass('Senha do MySQL (não será salva): ')}
        report = mysql_copy(credentials, args.destination, args.owner_for_unassigned)
    except Exception as exc:
        # Don't dump a traceback, connection object, hashes or source records.
        parser.exit(1, f'{exc}\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
