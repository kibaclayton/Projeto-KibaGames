import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Nexus Wolf's — serviço local")
    parser.add_argument('--data-dir', type=Path, help='Diretório do SQLite e imagens (padrão: LOCALAPPDATA/NexusWolfs).')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    import uvicorn
    from .api import create_app
    uvicorn.run(create_app(args.data_dir), host='127.0.0.1', port=args.port, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
