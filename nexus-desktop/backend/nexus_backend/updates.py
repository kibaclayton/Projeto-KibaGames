"""Atualização do aplicativo instalado, com confirmação e reversão.

Canal: uma pasta (a pasta `release` do projeto, por exemplo) ou uma URL HTTPS com `atualizacao.json`, que descreve
a versão mais nova: build, arquivo ZIP, SHA-256 e tamanho. Fluxo: verificar → preparar (baixar, conferir o hash,
extrair ao lado da instalação e rodar o autoteste da versão nova) → aplicar (um script externo troca as pastas
depois que o aplicativo fecha e reabre o Nexus) → reverter (o script devolve a pasta anterior). Nada é aplicado
sem a pessoa confirmar, e a versão anterior fica guardada até a próxima atualização.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urljoin, urlsplit
import zipfile

from .images import fetch

MANIFEST_NAME = 'atualizacao.json'
MAX_MANIFEST_BYTES = 256 * 1024
MAX_PACKAGE_BYTES = 400 * 1024 * 1024
UPDATE_SCRIPT = 'atualizar.ps1'


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run_self_test(exe: Path, data_dir: Path) -> dict:
    """Executa a versão nova com --self-test numa pasta de dados descartável; falhar aqui impede a troca."""
    report = data_dir / 'autoteste.json'
    completed = subprocess.run([str(exe), '--self-test', str(report), '--data-dir', str(data_dir)], capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if completed.returncode != 0 or not report.is_file():
        raise ValueError('A versão nova falhou no autoteste e não será aplicada.')
    result = json.loads(report.read_text(encoding='utf-8'))
    if result.get('status') != 'ok' or not result.get('frontend'):
        raise ValueError('A versão nova não passou na verificação de abertura.')
    return result


class Updater:
    def __init__(self, app_dir: Path, data_dir: Path, current: dict, channel: str | None, exe_name: str, verify=run_self_test, spawn=subprocess.Popen):
        self.app_dir = Path(app_dir)
        self.data_dir = Path(data_dir)
        self.current = current
        self.channel = channel or ''
        self.exe_name = exe_name
        self.verify = verify
        self.spawn = spawn
        self.lock = threading.Lock()
        self.available: dict | None = None
        self.staged: dict | None = None
        self.error = ''

    # Pastas irmãs da instalação: "<app>.novo" guarda a versão preparada, "<app>.anterior" a versão substituída.
    @property
    def staging_dir(self) -> Path:
        return self.app_dir.parent / (self.app_dir.name + '.novo')

    @property
    def previous_dir(self) -> Path:
        return self.app_dir.parent / (self.app_dir.name + '.anterior')

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / 'atualizacoes'

    def status(self) -> dict:
        staged = self.staged if self.staged and (self.staging_dir / self.exe_name).is_file() else None
        previous = None
        if self.previous_dir.is_dir():
            try:
                previous = json.loads((self.previous_dir / 'versao.json').read_text(encoding='utf-8-sig'))
            except (OSError, ValueError):
                previous = {'build': 'desconhecido'}
        return {'instalado': True, 'versao': self.current.get('versao'), 'build': self.current.get('build'), 'canal': self.channel, 'canal_configurado': bool(self.channel),
                'disponivel': self.available, 'preparada': staged, 'anterior': previous, 'erro': self.error}

    def _is_url(self) -> bool:
        return self.channel.lower().startswith('https://')

    def _read_manifest(self) -> dict:
        if not self.channel:
            raise ValueError('Nenhum canal de atualização configurado.')
        if self._is_url():
            host = urlsplit(self.channel).hostname or ''
            _, data = fetch(urljoin(self.channel, MANIFEST_NAME), 'application/json', ('application/json', 'text/plain', 'application/octet-stream'), MAX_MANIFEST_BYTES, {host}, 20)
        else:
            path = Path(self.channel) / MANIFEST_NAME
            if not path.is_file():
                raise ValueError('O canal de atualização não tem um atualizacao.json.')
            data = path.read_bytes()
        manifest = json.loads(data.decode('utf-8-sig'))  # tolera BOM de arquivos gravados pelo PowerShell
        for key in ('versao', 'build', 'arquivo', 'sha256', 'tamanho'):
            if key not in manifest:
                raise ValueError('Manifesto de atualização incompleto.')
        if not isinstance(manifest['arquivo'], str) or '/' in manifest['arquivo'] or '\\' in manifest['arquivo'] or not manifest['arquivo'].endswith('.zip'):
            raise ValueError('Manifesto de atualização inválido.')
        return manifest

    def check(self) -> dict | None:
        with self.lock:
            try:
                manifest = self._read_manifest()
                self.error = ''
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                self.error = f'Não foi possível consultar o canal: {exc}'
                self.available = None
                raise ValueError(self.error) from exc
            newer = str(manifest['build']) > str(self.current.get('build', ''))
            self.available = {**manifest, 'nova': newer} if newer else {**manifest, 'nova': False}
            return self.available

    def _obtain_package(self, manifest: dict) -> Path:
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        target = self.downloads_dir / manifest['arquivo']
        if target.is_file() and file_sha256(target) == manifest['sha256']:
            return target
        if self._is_url():
            host = urlsplit(self.channel).hostname or ''
            _, data = fetch(urljoin(self.channel, manifest['arquivo']), 'application/zip', ('application/zip', 'application/octet-stream', 'application/x-zip-compressed'), MAX_PACKAGE_BYTES, {host}, 600)
            target.write_bytes(data)
        else:
            source = Path(self.channel) / manifest['arquivo']
            if not source.is_file():
                raise ValueError('O arquivo da atualização não foi encontrado no canal.')
            shutil.copyfile(source, target)
        if file_sha256(target) != manifest['sha256']:
            target.unlink(missing_ok=True)
            raise ValueError('O arquivo baixado está corrompido (SHA-256 diferente do manifesto).')
        return target

    def prepare(self) -> dict:
        """Baixa, confere, extrai em "<app>.novo" e roda o autoteste; só então a atualização pode ser aplicada."""
        with self.lock:
            manifest = self.available if self.available and self.available.get('nova') else None
            if not manifest:
                raise ValueError('Verifique as atualizações antes de preparar.')
            package = self._obtain_package(manifest)
            if self.staging_dir.exists():
                shutil.rmtree(self.staging_dir, ignore_errors=True)
            self.staging_dir.mkdir(parents=True)
            try:
                with zipfile.ZipFile(package) as archive:
                    for member in archive.namelist():
                        if member.startswith('/') or '..' in member.split('/'):
                            raise ValueError('O pacote de atualização contém caminhos inválidos.')
                    archive.extractall(self.staging_dir)
                exe = self.staging_dir / self.exe_name
                if not exe.is_file():
                    raise ValueError(f'O pacote não contém {self.exe_name}.')
                version = json.loads((self.staging_dir / 'versao.json').read_text(encoding='utf-8-sig'))
                if str(version.get('build')) != str(manifest['build']):
                    raise ValueError('O pacote não corresponde ao manifesto.')
                self._carry_install_files(manifest)
                with tempfile.TemporaryDirectory(prefix='nexus-autoteste-') as temporary:
                    self.verify(exe, Path(temporary))
            except Exception:
                shutil.rmtree(self.staging_dir, ignore_errors=True)
                raise
            self.staged = {**manifest, 'pasta': str(self.staging_dir)}
            return self.staged

    def _carry_install_files(self, manifest: dict):
        """O pacote traz só a aplicação; o marcador da instalação e o desinstalador do Inno vêm da pasta atual."""
        for extra in list(self.app_dir.glob('unins*')) + [self.app_dir / 'instalado.json']:
            if extra.is_file():
                shutil.copy2(extra, self.staging_dir / extra.name)
        marker = self.staging_dir / 'instalado.json'
        if marker.is_file():
            data = json.loads(marker.read_text(encoding='utf-8-sig'))
            data['build'] = manifest['build']
            marker.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _script(self) -> Path:
        bundled = Path(getattr(sys, '_MEIPASS', self.app_dir)) / UPDATE_SCRIPT
        if not bundled.is_file():
            bundled = Path(__file__).resolve().parent.parent.parent / 'scripts' / UPDATE_SCRIPT
        if not bundled.is_file():
            raise ValueError('O script de atualização não foi encontrado.')
        copy = Path(tempfile.gettempdir()) / f'nexus-{UPDATE_SCRIPT}'
        shutil.copyfile(bundled, copy)
        return copy

    def _launch(self, *extra: str):
        script = self._script()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        log = self.data_dir / 'atualizacao.log'
        command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', str(script),
                   '-Instalacao', str(self.app_dir), '-Nova', str(self.staging_dir), '-ProcessId', str(os.getpid()), '-Exe', self.exe_name, '-Log', str(log), *extra]
        # O aplicativo não tem console: o PowerShell precisa de entrada/saída válidas (arquivo de log) e de um grupo de
        # processos próprio, senão nem inicia. Sem DETACHED_PROCESS, que o impedia de criar seu host de console.
        with open(log, 'a', encoding='utf-8') as stream:
            stream.write(f'[{__import__("datetime").datetime.now():%Y-%m-%d %H:%M:%S}] Disparando: {" ".join(command)}\n')
        output = open(self.data_dir / 'atualizacao-powershell.log', 'ab')
        try:
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            self.spawn(command, cwd=str(tempfile.gettempdir()), creationflags=flags, close_fds=False, stdin=subprocess.DEVNULL, stdout=output, stderr=output)
        finally:
            output.close()
        return command

    def apply(self) -> dict:
        with self.lock:
            if not self.staged or not (self.staging_dir / self.exe_name).is_file():
                raise ValueError('Nenhuma atualização preparada.')
            command = self._launch()
            return {'aplicando': self.staged.get('build'), 'comando': command}

    def rollback(self) -> dict:
        with self.lock:
            if not (self.previous_dir / self.exe_name).is_file():
                raise ValueError('Não há versão anterior guardada.')
            command = self._launch('-Reverter')
            return {'revertendo': True, 'comando': command}
