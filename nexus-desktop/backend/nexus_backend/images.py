import hashlib
import http.client
import io
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import time
from urllib.parse import urljoin, urlsplit
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from .models import Crop

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
SIZES = {'capa': (900, 1200), 'colecao': (900, 900), 'avatar': (512, 512)}
IMAGE_SLOTS = threading.BoundedSemaphore(2)


def validated_address(url: str) -> tuple[str, str, str]:
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('Use um link direto HTTPS para a imagem, sem credenciais ou portas alternativas.')
    host = parts.hostname.encode('idna').decode('ascii')
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('O endereço da imagem precisa ser público.')
    path = parts.path or '/'
    if parts.query:
        path += '?' + parts.query
    return host, sorted(addresses)[0], path


class PinnedHTTPS(http.client.HTTPSConnection):
    """Connect only to a validated IP; retain the hostname for TLS and Host."""
    def __init__(self, host, ip):
        super().__init__(host, timeout=8, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        raw = socket.create_connection((self.ip, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def download_image(url: str) -> bytes:
    deadline = time.monotonic() + 25
    for _ in range(4):
        host, ip, path = validated_address(url)
        connection = PinnedHTTPS(host, ip)
        try:
            connection.request('GET', path, headers={'User-Agent': 'NexusWolfs/0.2', 'Accept': 'image/png,image/jpeg,image/webp'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Redirecionamento sem destino.')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f'O servidor da imagem respondeu HTTP {response.status}.')
            if response.getheader('Content-Type', '').split(';')[0].lower() not in ('image/jpeg', 'image/png', 'image/webp'):
                raise ValueError('O link deve apontar à imagem, não a uma página do Google ou de outro site.')
            if int(response.getheader('Content-Length', '0')) > MAX_BYTES:
                raise ValueError('A imagem deve ter até 10 MB.')
            data = bytearray()
            while chunk := response.read(min(65536, MAX_BYTES + 1 - len(data))):
                data.extend(chunk)
                if len(data) > MAX_BYTES or time.monotonic() > deadline:
                    raise ValueError('Download muito grande ou demorado.')
            return bytes(data)
        finally:
            connection.close()
    raise ValueError('A imagem redirecionou muitas vezes.')


def convert_image(data: bytes, kind: str, crop: Crop | None = None) -> tuple[bytes, bytes, int, int]:
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Envie uma imagem de até 10 MB.')
    if kind not in SIZES:
        raise ValueError('Tipo de imagem inválido.')
    with IMAGE_SLOTS, warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('Use imagens JPEG, PNG ou WebP.')
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError('A imagem deve ter até 20 megapixels.')
                if getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Use uma imagem estática.')
                picture = ImageOps.exif_transpose(source).convert('RGB')
            if crop:
                if crop.x + crop.width > picture.width or crop.y + crop.height > picture.height:
                    raise ValueError('Recorte fora dos limites da imagem.')
                picture = picture.crop((crop.x, crop.y, crop.x + crop.width, crop.y + crop.height))
            if kind in ('avatar', 'colecao'):
                # A square file; circular appearance is applied by the UI.
                side = min(SIZES[kind][0], picture.width, picture.height)
                picture = ImageOps.fit(picture, (side, side), method=Image.Resampling.LANCZOS)
            else:
                picture.thumbnail(SIZES[kind], Image.Resampling.LANCZOS)
            full = io.BytesIO()
            picture.save(full, 'WEBP', quality=85, method=4, exif=b'')
            thumbnail = picture.copy()
            thumbnail.thumbnail((240, 320) if kind == 'capa' else (160, 160), Image.Resampling.LANCZOS)
            small = io.BytesIO()
            thumbnail.save(small, 'WEBP', quality=85, method=4, exif=b'')
            return full.getvalue(), small.getvalue(), picture.width, picture.height
        except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise ValueError('Imagem inválida ou excedendo os limites de segurança.') from exc


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def store_image(conn, directory: Path, user_id: int, kind: str, data: bytes, crop: Crop | None = None):
    full, thumbnail, width, height = convert_image(data, kind, crop)
    image_id = hashlib.sha256(f'{user_id}:{kind}:'.encode() + full).hexdigest()
    for suffix, content in (('', full), ('.thumb', thumbnail)):
        path = directory / 'images' / f'{image_id}{suffix}.webp'
        if not path.exists():
            atomic_write(path, content)
    conn.execute('INSERT OR IGNORE INTO imagens(id,usuario_id,tipo,largura,altura,bytes) VALUES(?,?,?,?,?,?)',
                 (image_id, user_id, kind, width, height, len(full)))
    return {'id': image_id, 'tipo': kind, 'largura': width, 'altura': height, 'bytes': len(full), 'miniatura_bytes': len(thumbnail)}

