"""Backup, restauração, integridade e limpeza de imagens órfãs.

Um backup é um ZIP com um instantâneo consistente de `nexus.sqlite3` (API de backup do SQLite, segura com o
aplicativo aberto), a pasta `images/` e um `manifesto.json` com versão, contagens e o SHA-256 de cada arquivo.
Certificados, chaves e a preferência de acesso pela rede ficam de fora: são deste computador, não da biblioteca.

A restauração só aceita arquivos da pasta `backups/` dentro da pasta de dados, valida hashes e integridade antes de
tocar em qualquer coisa, faz um backup de segurança do estado atual e troca os arquivos por renomeação.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
import zipfile

from .database import SCHEMA_VERSION, Database

BACKUP_DIR = 'backups'
BACKUP_NAME = re.compile(r'^nexus-backup-\d{8}-\d{6}(-[a-z-]+)?\.zip$')
MAINTENANCE = threading.Lock()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _stamp() -> str:
    # Hora local no nome do arquivo, para bater com o que a pessoa vê no relógio; o manifesto guarda o instante em UTC.
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def backups_directory(db: Database) -> Path:
    return db.directory / BACKUP_DIR


def _remove_tree(path: Path, attempts: int = 5) -> bool:
    """No Windows um arquivo aberto (uma miniatura sendo servida) impede a remoção; tenta de novo com espera."""
    for attempt in range(attempts):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        time.sleep(0.2 * (attempt + 1))
    return not path.exists()


def cleanup_leftovers(db: Database):
    """Pastas de preparo ou de versão anterior que sobraram de uma restauração interrompida ou de arquivos em uso."""
    for leftover in list(db.directory.glob('.restaurando-*')) + list(db.directory.glob('.anterior-*')):
        if leftover.is_dir():
            _remove_tree(leftover, attempts=1)
        else:
            try:
                leftover.unlink()
            except OSError:
                pass


def _counts(conn) -> dict:
    return {table: conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('usuarios', 'jogos', 'colecoes', 'imagens', 'avatares')}


def create_backup(db: Database, reason: str = 'manual') -> dict:
    """Instantâneo consistente do banco + imagens, com manifesto e hashes, escrito de forma atômica."""
    folder = backups_directory(db)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = f'-{reason}' if reason and reason != 'manual' else ''
    name = f'nexus-backup-{_stamp()}{suffix}.zip'
    target = folder / name
    counter = 1
    while target.exists():
        counter += 1
        target = folder / f'nexus-backup-{_stamp()}{suffix}-{counter}.zip'
    snapshot = folder / f'.{target.stem}.sqlite3'
    temporary = folder / f'.{target.name}.tmp'
    try:
        source, copy = sqlite3.connect(db.path), sqlite3.connect(snapshot)
        try:
            source.backup(copy)
            version = copy.execute('PRAGMA user_version').fetchone()[0]
            counts = _counts(copy)
        finally:
            copy.close()
            source.close()
        files = {'nexus.sqlite3': _sha256(snapshot)}
        images_dir = db.directory / 'images'
        image_files = sorted(p for p in images_dir.glob('*.webp')) if images_dir.is_dir() else []
        for image in image_files:
            files[f'images/{image.name}'] = _sha256(image)
        manifest = {'formato': 'nexus-wolfs-backup', 'versao_formato': 1, 'aplicativo': '0.3.0', 'esquema': version, 'criado': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'motivo': reason, 'contagens': counts, 'arquivos': files}
        with zipfile.ZipFile(temporary, 'w') as archive:
            archive.writestr('manifesto.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.write(snapshot, 'nexus.sqlite3', compress_type=zipfile.ZIP_DEFLATED)
            for image in image_files:
                archive.write(image, f'images/{image.name}', compress_type=zipfile.ZIP_STORED)
        os.replace(temporary, target)
    finally:
        snapshot.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
    return describe_backup(target)


def describe_backup(path: Path) -> dict:
    info = {'nome': path.name, 'bytes': path.stat().st_size, 'modificado': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec='seconds'), 'valido': False, 'manifesto': None, 'erro': ''}
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('manifesto.json'))
        if manifest.get('formato') != 'nexus-wolfs-backup':
            raise ValueError('Formato desconhecido.')
        info['manifesto'] = {k: manifest.get(k) for k in ('aplicativo', 'esquema', 'criado', 'motivo', 'contagens')}
        info['manifesto']['imagens_arquivos'] = sum(1 for k in manifest.get('arquivos', {}) if k.startswith('images/'))
        info['valido'] = True
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        info['erro'] = f'Arquivo inválido: {exc}'
    return info


def list_backups(db: Database) -> list[dict]:
    cleanup_leftovers(db)
    folder = backups_directory(db)
    if not folder.is_dir():
        return []
    return [describe_backup(path) for path in sorted(folder.glob('nexus-backup-*.zip'), key=lambda p: p.name, reverse=True)]


def backup_path(db: Database, name: str) -> Path:
    if not BACKUP_NAME.match(name):
        raise ValueError('Nome de backup inválido.')
    path = backups_directory(db) / name
    if not path.is_file() or path.resolve().parent != backups_directory(db).resolve():
        raise FileNotFoundError('Backup não encontrado.')
    return path


def delete_backup(db: Database, name: str):
    backup_path(db, name).unlink()


def validate_backup(path: Path, destination: Path) -> dict:
    """Extrai para `destination` conferindo cada hash do manifesto e a integridade do banco; falha sem tocar na biblioteca."""
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifesto.json'))
        if manifest.get('formato') != 'nexus-wolfs-backup' or 'nexus.sqlite3' not in manifest.get('arquivos', {}):
            raise ValueError('Este arquivo não é um backup do Nexus.')
        if int(manifest.get('esquema', 0)) > SCHEMA_VERSION:
            raise ValueError('Este backup foi feito por uma versão mais nova do Nexus.')
        names = set(archive.namelist())
        for member, expected in manifest['arquivos'].items():
            if member not in names or '..' in member or member.startswith('/'):
                raise ValueError(f'Arquivo ausente ou inválido no backup: {member}')
            out = destination / member
            out.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(out, 'wb') as target:
                shutil.copyfileobj(source, target)
            if _sha256(out) != expected:
                raise ValueError(f'O arquivo {member} está corrompido (hash diferente do manifesto).')
    conn = sqlite3.connect(destination / 'nexus.sqlite3')
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('O banco dentro do backup falhou na verificação de integridade.')
        if conn.execute("SELECT count(*) FROM sqlite_master WHERE name='usuarios'").fetchone()[0] != 1:
            raise ValueError('O banco dentro do backup não tem as tabelas do Nexus.')
    finally:
        conn.close()
    return manifest


def restore_backup(db: Database, name: str) -> dict:
    """Valida, faz backup de segurança do estado atual e troca banco e imagens por renomeação."""
    path = backup_path(db, name)
    stamp = _stamp()
    staging = db.directory / f'.restaurando-{stamp}'
    previous_db = db.directory / f'.anterior-{stamp}.sqlite3'
    previous_images = db.directory / f'.anterior-{stamp}-images'
    try:
        staging.mkdir(parents=True, exist_ok=False)
        manifest = validate_backup(path, staging)
        safety = create_backup(db, 'antes-de-restaurar')
        conn = sqlite3.connect(db.path)
        try:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            conn.close()
        images_dir = db.directory / 'images'
        if images_dir.exists():
            os.replace(images_dir, previous_images)
        if db.path.exists():
            os.replace(db.path, previous_db)
        for extra in (db.path.with_name(db.path.name + '-wal'), db.path.with_name(db.path.name + '-shm')):
            extra.unlink(missing_ok=True)
        os.replace(staging / 'nexus.sqlite3', db.path)
        staged_images = staging / 'images'
        if staged_images.is_dir():
            os.replace(staged_images, images_dir)
        else:
            images_dir.mkdir(exist_ok=True)
        db.initialize()  # aplica migrações se o backup for de um esquema anterior
        _remove_tree(previous_images)
        previous_db.unlink(missing_ok=True)
        return {'restaurado': name, 'backup_seguranca': safety['nome'], 'contagens': manifest.get('contagens')}
    finally:
        _remove_tree(staging)


def integrity(db: Database) -> dict:
    with db.connection() as conn:
        check = [row[0] for row in conn.execute('PRAGMA integrity_check')]
        foreign = [dict(zip(('tabela', 'linha', 'referencia', 'indice'), row)) for row in conn.execute('PRAGMA foreign_key_check')]
        counts = _counts(conn)
        version = conn.execute('PRAGMA user_version').fetchone()[0]
    return {'ok': check == ['ok'] and not foreign, 'integridade': check, 'chaves_estrangeiras': foreign, 'contagens': counts, 'esquema': version}


ORPHAN_SQL = """
SELECT id, bytes FROM imagens WHERE id NOT IN (SELECT capa_id FROM jogos WHERE capa_id IS NOT NULL)
 AND id NOT IN (SELECT avatar_id FROM usuarios WHERE avatar_id IS NOT NULL)
 AND id NOT IN (SELECT capa_id FROM colecoes WHERE capa_id IS NOT NULL)
 AND id NOT IN (SELECT imagem_id FROM avatares)
 AND id NOT IN (SELECT fundo_id FROM jogos WHERE fundo_id IS NOT NULL)
"""


def find_orphans(db: Database) -> dict:
    """Imagens sem uso: registros não referenciados por jogo, avatar ou coleção, e arquivos sem registro."""
    images_dir = db.directory / 'images'
    with db.connection() as conn:
        rows = [dict(r) for r in conn.execute(ORPHAN_SQL)]
        known = {r['id'] for r in conn.execute('SELECT id FROM imagens')}
    stray = []
    if images_dir.is_dir():
        for file in images_dir.glob('*.webp'):
            image_id = file.name.split('.')[0]
            if image_id not in known:
                stray.append({'arquivo': file.name, 'bytes': file.stat().st_size})
    bytes_on_disk = 0
    for row in rows:
        for suffix in ('', '.thumb'):
            file = images_dir / f"{row['id']}{suffix}.webp"
            if file.is_file():
                bytes_on_disk += file.stat().st_size
    return {'registros': len(rows), 'arquivos_sem_registro': len(stray), 'bytes': bytes_on_disk + sum(s['bytes'] for s in stray)}


def clean_orphans(db: Database) -> dict:
    safety = create_backup(db, 'antes-de-limpar')
    images_dir = db.directory / 'images'
    removed_rows = removed_files = freed = 0
    with db.connection() as conn:
        rows = [dict(r) for r in conn.execute(ORPHAN_SQL)]
        for row in rows:
            conn.execute('DELETE FROM imagens WHERE id=?', (row['id'],))
            removed_rows += 1
            for suffix in ('', '.thumb'):
                file = images_dir / f"{row['id']}{suffix}.webp"
                if file.is_file():
                    freed += file.stat().st_size
                    file.unlink()
                    removed_files += 1
        known = {r['id'] for r in conn.execute('SELECT id FROM imagens')}
    if images_dir.is_dir():
        for file in images_dir.glob('*.webp'):
            if file.name.split('.')[0] not in known:
                freed += file.stat().st_size
                file.unlink()
                removed_files += 1
    return {'registros_removidos': removed_rows, 'arquivos_removidos': removed_files, 'bytes_liberados': freed, 'backup_seguranca': safety['nome']}
