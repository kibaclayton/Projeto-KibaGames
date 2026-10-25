"""Windowed Windows entry point. No credentials or data are embedded in the executable."""
import argparse
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.request import urlopen

from nexus_backend.api import create_app
from nexus_backend.runtime import attach_frontend, choose_data_directory, import_previous_data, install_info, installed_data_directory, version_info
from nexus_backend.updates import Updater

PREFERRED_PORT = 48765


def bind_listener(port: int) -> socket.socket:
    """Usa a porta preferida quando livre; se outra instância ou programa a ocupar, cai para uma porta dinâmica."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(('127.0.0.1', port))
    except OSError:
        listener.close()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
    return listener


def locations():
    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).resolve().parent
        # Modo portátil: release/<build>/NexusWolfs.exe; os dados ficam no projeto, fora das releases.
        project = app_dir.parent.parent
        frontend = Path(sys._MEIPASS) / 'frontend'
    else:
        app_dir = Path(__file__).resolve().parent
        project = app_dir.parent
        frontend = project / 'dist'
    return app_dir, project, frontend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path)
    # A porta fixa mantém a mesma origem entre aberturas, o que o navegador exige para "lembrar neste aparelho".
    parser.add_argument('--port', type=int, default=PREFERRED_PORT)
    parser.add_argument('--serve-only', action='store_true')
    parser.add_argument('--self-test', type=Path, help='Write a smoke-test report and exit without opening a window.')
    args = parser.parse_args()
    app_dir, project, frontend = locations()
    installed = install_info(app_dir)
    version = version_info(app_dir)
    imported = False
    if args.data_dir:
        data_dir = args.data_dir
    elif installed:
        data_dir = installed_data_directory(installed)
        previous = installed.get('dados_anteriores')
        if isinstance(previous, str) and previous:
            imported = import_previous_data(data_dir, Path(previous))
    else:
        data_dir = choose_data_directory(project)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / 'runtime.log'
    logging.basicConfig(filename=log_file, level=logging.WARNING, encoding='utf-8')
    if imported:
        logging.warning('Biblioteca importada da instalação portátil para %s', data_dir)
    import uvicorn
    app = create_app(data_dir)
    attach_frontend(app, frontend)
    app.state.runtime = {'instalado': installed is not None, 'versao': version.get('versao', '0.3.0'), 'build': version.get('build', 'dev'), 'pasta_dados': str(data_dir), 'pasta_app': str(app_dir), 'importado': imported}
    if installed and getattr(sys, 'frozen', False):
        app.state.updater = Updater(app_dir, data_dir, version, installed.get('canal'), Path(sys.executable).name)
    listener = bind_listener(args.port)
    port = listener.getsockname()[1]
    config = uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_config=None, log_level='warning')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    address = f'http://127.0.0.1:{port}'
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Não foi possível iniciar o serviço local. Consulte runtime.log na pasta de dados.')
            time.sleep(.05)
        if args.self_test:
            with urlopen(address + '/api/saude', timeout=5) as response:
                health = json.load(response)
            with urlopen(address, timeout=5) as response:
                html = response.read().decode()
            import webview  # Also validate the packaged Python module and native loader.
            from webview.platforms import winforms
            report = {'status': health['status'], 'version': health['versao'], 'frontend': 'Nexus Wolf' in html,
                      'webview_module': bool(webview), 'winforms': bool(winforms), 'data_directory': str(data_dir), 'build': app.state.runtime['build']}
            args.self_test.write_text(json.dumps(report, indent=2), encoding='utf-8')
        elif args.serve_only:
            app.state.shutdown = lambda: setattr(server, 'should_exit', True)
            app.state.network.start_if_enabled()
            print(address, flush=True)
            thread.join()
        else:
            app.state.network.start_if_enabled()
            import webview
            window = webview.create_window("Nexus Wolf's", address, width=1440, height=960, min_size=(800, 600), background_color='#0A0B10', text_select=True)
            # O atualizador pede o fechamento da janela depois de agendar a troca de versão.
            app.state.shutdown = window.destroy
            # No exposed Python/JS bridge; all operations use the authenticated HTTP API.
            webview.start(gui='edgechromium', private_mode=False, storage_path=str(data_dir / 'webview'))
    finally:
        app.state.network.stop()
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        logging.exception('Falha ao abrir Nexus')
        if '--self-test' in sys.argv or '--serve-only' in sys.argv:
            raise
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f'Não foi possível abrir o Nexus.\n{exc}', 'Nexus Wolf’s', 0x10)
        else:
            raise
