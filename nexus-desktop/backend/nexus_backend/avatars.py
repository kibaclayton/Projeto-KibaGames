"""Galeria de até cinco fotos por perfil e busca de imagens no Wikimedia Commons.

A galeria é por perfil (tabela `avatares`, posições 1 a 5); a foto ativa continua em `usuarios.avatar_id`, que é o único
dado público (miniatura no seletor de perfis). As demais fotos só aparecem para o próprio perfil autenticado. A busca no
Commons devolve imagens reais com licença e autor; a imagem escolhida passa pelo proxy de prévia, é recortada na
interface e enviada como qualquer upload, com as validações de sempre.
"""
import html
import re
from urllib.parse import urlencode, urlsplit

from fastapi import HTTPException

from .images import fetch

SLOTS = 5
COMMONS_HOSTS = {'commons.wikimedia.org'}
COMMONS_IMAGE_HOSTS = {'upload.wikimedia.org'}
MAX_JSON_BYTES = 1024 * 1024


def gallery(conn, user_id: int) -> list[dict]:
    active = conn.execute('SELECT avatar_id FROM usuarios WHERE id=?', (user_id,)).fetchone()['avatar_id']
    rows = {row['posicao']: row['imagem_id'] for row in conn.execute('SELECT posicao, imagem_id FROM avatares WHERE usuario_id=? ORDER BY posicao', (user_id,))}
    return [{'posicao': slot, 'imagem_id': rows.get(slot), 'ativo': bool(rows.get(slot)) and rows.get(slot) == active} for slot in range(1, SLOTS + 1)]


def ensure_in_gallery(conn, user_id: int, image_id: str) -> int:
    """Garante que a imagem esteja na galeria do perfil; usa a primeira posição livre ou recusa com 409 quando cheia."""
    existing = conn.execute('SELECT posicao FROM avatares WHERE usuario_id=? AND imagem_id=?', (user_id, image_id)).fetchone()
    if existing:
        return existing['posicao']
    used = {row['posicao'] for row in conn.execute('SELECT posicao FROM avatares WHERE usuario_id=?', (user_id,))}
    free = next((slot for slot in range(1, SLOTS + 1) if slot not in used), None)
    if free is None:
        raise HTTPException(409, 'A galeria já tem cinco fotos. Escolha qual substituir.')
    conn.execute('INSERT INTO avatares(usuario_id, posicao, imagem_id) VALUES(?,?,?)', (user_id, free, image_id))
    return free


def set_slot(conn, user_id: int, slot: int, image_id: str) -> list[dict]:
    """Coloca (ou substitui) a foto de uma posição; se a foto substituída era a ativa, a nova passa a ser a ativa."""
    previous = conn.execute('SELECT imagem_id FROM avatares WHERE usuario_id=? AND posicao=?', (user_id, slot)).fetchone()
    conn.execute('DELETE FROM avatares WHERE usuario_id=? AND imagem_id=? AND posicao<>?', (user_id, image_id, slot))
    conn.execute('INSERT OR REPLACE INTO avatares(usuario_id, posicao, imagem_id) VALUES(?,?,?)', (user_id, slot, image_id))
    active = conn.execute('SELECT avatar_id FROM usuarios WHERE id=?', (user_id,)).fetchone()['avatar_id']
    if previous and previous['imagem_id'] == active:
        conn.execute('UPDATE usuarios SET avatar_id=? WHERE id=?', (image_id, user_id))
    return gallery(conn, user_id)


def remove_slot(conn, user_id: int, slot: int) -> list[dict]:
    """Remove a foto da posição. Se era a ativa, ativa a próxima foto da galeria ou volta ao avatar padrão."""
    row = conn.execute('SELECT imagem_id FROM avatares WHERE usuario_id=? AND posicao=?', (user_id, slot)).fetchone()
    if not row:
        raise HTTPException(404, 'Posição vazia.')
    conn.execute('DELETE FROM avatares WHERE usuario_id=? AND posicao=?', (user_id, slot))
    active = conn.execute('SELECT avatar_id FROM usuarios WHERE id=?', (user_id,)).fetchone()['avatar_id']
    if active == row['imagem_id']:
        replacement = conn.execute('SELECT imagem_id FROM avatares WHERE usuario_id=? ORDER BY posicao LIMIT 1', (user_id,)).fetchone()
        conn.execute('UPDATE usuarios SET avatar_id=? WHERE id=?', (replacement['imagem_id'] if replacement else None, user_id))
    return gallery(conn, user_id)


def _text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ''
    clean = html.unescape(re.sub(r'<[^<>]{0,500}>', ' ', value[:limit * 4]))
    return re.sub(r'\s+', ' ', clean).strip()[:limit]


def _allowed(url) -> bool:
    parts = urlsplit(url if isinstance(url, str) else '')
    return parts.scheme == 'https' and parts.hostname in COMMONS_IMAGE_HOSTS and not parts.username and parts.port in (None, 443)


def search_commons(term: str, fetch_json=None) -> list[dict]:
    """Imagens do Wikimedia Commons (arquivos JPEG/PNG), com miniatura de 1024 px, página de origem, licença e autor."""
    params = {'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': term + ' filetype:bitmap', 'gsrnamespace': 6, 'gsrlimit': 12,
              'prop': 'imageinfo|info', 'iiprop': 'url|extmetadata|mime', 'iiurlwidth': 1024, 'iiextmetadatafilter': 'LicenseShortName|Artist|ImageDescription', 'inprop': 'url'}
    url = 'https://commons.wikimedia.org/w/api.php?' + urlencode(params)
    if fetch_json is None:
        import json
        content_type, data = fetch(url, 'application/json', ('application/json',), MAX_JSON_BYTES, COMMONS_HOSTS, 8)
        result = json.loads(data)
    else:
        result = fetch_json(url, COMMONS_HOSTS)
    pages = result.get('query', {}).get('pages', {}) if isinstance(result, dict) else {}
    items = []
    for page in sorted(pages.values(), key=lambda p: p.get('index', 999)) if isinstance(pages, dict) else []:
        info = page.get('imageinfo', [{}])[0] if isinstance(page.get('imageinfo'), list) and page['imageinfo'] else {}
        thumb, full, mime = info.get('thumburl'), info.get('url'), info.get('mime', '')
        if mime not in ('image/jpeg', 'image/png') or not _allowed(thumb) or not _allowed(full):
            continue
        meta = info.get('extmetadata', {}) if isinstance(info.get('extmetadata'), dict) else {}
        license_name = _text(meta.get('LicenseShortName', {}).get('value'), 60)
        author = _text(meta.get('Artist', {}).get('value'), 80)
        title = _text(page.get('title', ''), 150).removeprefix('File:').removeprefix('Ficheiro:')
        origin = page.get('fullurl') if isinstance(page.get('fullurl'), str) and page['fullurl'].startswith('https://commons.wikimedia.org/') else 'https://commons.wikimedia.org/wiki/' + str(page.get('title', ''))
        items.append({'titulo': title, 'previa': thumb, 'imagem': thumb, 'origem': origin, 'licenca': license_name or 'ver página de origem', 'autor': author})
    return items[:12]
