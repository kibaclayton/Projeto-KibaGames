"""Packaged desktop startup and static frontend integration."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3

from fastapi.staticfiles import StaticFiles

from .database import data_directory

INSTALL_MARKER = 'instalado.json'
VERSION_FILE = 'versao.json'


def choose_data_directory(project: Path) -> Path:
    imported = project / 'data' / 'biblioteca-importada'
    return imported if (imported / 'nexus.sqlite3').is_file() else project / 'data' / 'biblioteca'


def attach_frontend(app, directory: Path):
    if not (directory / 'index.html').is_file():
        raise RuntimeError('Interface não compilada. Execute pnpm build antes de abrir o aplicativo.')
    # StaticFiles enforces containment; the data directory is never mounted.
    app.mount('/', StaticFiles(directory=directory, html=True), name='frontend')


def read_json(path: Path) -> dict | None:
    # utf-8-sig aceita arquivos com BOM, como os que o PowerShell 5.1 grava com -Encoding utf8.
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def install_info(app_dir: Path) -> dict | None:
    """Marcador escrito pelo instalador ao lado do executável; ausente no modo portátil (pasta release do projeto)."""
    info = read_json(app_dir / INSTALL_MARKER)
    return info if info and info.get('instalado') is True else None


def version_info(app_dir: Path) -> dict:
    """`versao.json` é gravado pelo build ao lado do executável; no modo de desenvolvimento não existe."""
    return read_json(app_dir / VERSION_FILE) or {'versao': '0.3.0', 'build': 'dev', 'exe': ''}


def installed_data_directory(info: dict) -> Path:
    custom = info.get('dados')
    return Path(custom) if isinstance(custom, str) and custom else data_directory()


def import_previous_data(target: Path, source: Path) -> bool:
    """Primeira abertura do aplicativo instalado: copia a biblioteca portátil existente, sem mover nem alterar a origem.

    Copia o banco por um instantâneo consistente, as imagens, os certificados (para o celular continuar confiando) e a
    preferência de acesso pela rede. Backups e dados do navegador ficam na origem.
    """
    if (target / 'nexus.sqlite3').exists() or not (source / 'nexus.sqlite3').is_file():
        return False
    target.mkdir(parents=True, exist_ok=True)
    origin, copy = sqlite3.connect(source / 'nexus.sqlite3'), sqlite3.connect(target / 'nexus.sqlite3')
    try:
        origin.backup(copy)
    finally:
        copy.close()
        origin.close()
    for folder in ('images', 'certificados'):
        if (source / folder).is_dir():
            shutil.copytree(source / folder, target / folder, dirs_exist_ok=True)
    if (source / 'acesso-rede.json').is_file():
        shutil.copy2(source / 'acesso-rede.json', target / 'acesso-rede.json')
    (target / 'importacao.json').write_text(json.dumps({'origem': str(source), 'quando': datetime.now(timezone.utc).isoformat(timespec='seconds')}, ensure_ascii=False, indent=2), encoding='utf-8')
    return True
