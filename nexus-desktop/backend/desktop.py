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
from nexus_backend.runtime import attach_frontend, choose_data_directory


def locations():
    if getattr(sys, 'frozen', False):
        # release/NexusWolfs/NexusWolfs.exe; data remains in the project, outside releases.
        project = Path(sys.executable).resolve().parents[2]
        frontend = Path(sys._MEIPASS) / 'frontend'
    else:
        project = Path(__file__).resolve().parent.parent
        frontend = project / 'dist'
    return project, frontend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--serve-only', action='store_true')
    parser.add_argument('--self-test', type=Path, help='Write a smoke-test report and exit without opening a window.')
    args = parser.parse_args()
    project, frontend = locations()
    data_dir = args.data_dir or choose_data_directory(project)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / 'runtime.log'
    logging.basicConfig(filename=log_file, level=logging.WARNING, encoding='utf-8')
    import uvicorn
    app = create_app(data_dir)
    attach_frontend(app, frontend)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', args.port))
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
                      'webview_module': bool(webview), 'winforms': bool(winforms), 'data_directory': str(data_dir)}
            args.self_test.write_text(json.dumps(report, indent=2), encoding='utf-8')
        elif args.serve_only:
            print(address, flush=True)
            thread.join()
        else:
            import webview
            webview.create_window("Nexus Wolf's", address, width=1440, height=960, min_size=(800, 600), background_color='#0A0B10', text_select=True)
            # No exposed Python/JS bridge; all operations use the authenticated HTTP API.
            webview.start(gui='edgechromium', private_mode=False, storage_path=str(data_dir / 'webview'))
    finally:
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
