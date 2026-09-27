"""Packaged desktop startup and static frontend integration."""
from pathlib import Path
from fastapi.staticfiles import StaticFiles


def choose_data_directory(project: Path) -> Path:
    imported = project / 'data' / 'biblioteca-importada'
    return imported if (imported / 'nexus.sqlite3').is_file() else project / 'data' / 'biblioteca'


def attach_frontend(app, directory: Path):
    if not (directory / 'index.html').is_file():
        raise RuntimeError('Interface não compilada. Execute pnpm build antes de abrir o aplicativo.')
    # StaticFiles enforces containment; the data directory is never mounted.
    app.mount('/', StaticFiles(directory=directory, html=True), name='frontend')
