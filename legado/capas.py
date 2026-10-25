"""Busca imagens de jogos na Wikipedia sem exigir chave de API."""
import io
import json
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from PIL import Image, ImageOps


def download(url, limit=6_000_000):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('en.wikipedia.org', 'upload.wikimedia.org'):
        raise ValueError('Endereço de imagem não permitido.')
    request = Request(url, headers={'User-Agent': 'MinhaBibliotecaJogos/1.1 (personal desktop game library)'})
    with urlopen(request, timeout=12) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('A imagem excede o tamanho permitido.')
    return data


def buscar_capas(nome):
    params = dict(action='query', format='json', generator='search',
                  gsrsearch=nome + ' video game', gsrnamespace=0, gsrlimit=5,
                  prop='pageimages', piprop='thumbnail', pithumbsize=500, pilicense='any')
    result = json.loads(download('https://en.wikipedia.org/w/api.php?' + urlencode(params)))
    if 'error' in result:
        raise ValueError('O serviço de busca está indisponível. Tente novamente mais tarde.')
    pages = sorted(result.get('query', {}).get('pages', {}).values(), key=lambda p: p.get('index', 999))
    candidates = []
    for page in pages:
        url = page.get('thumbnail', {}).get('source')
        if not url:
            continue
        candidates.append({'title': page['title'], 'url': url})
    return candidates


def baixar_capa(url):
    with Image.open(io.BytesIO(download(url))) as source:
        picture = ImageOps.exif_transpose(source).convert('RGB')
        picture.thumbnail((900, 1200))
        output = io.BytesIO()
        picture.save(output, format='JPEG', quality=88)
        return output.getvalue()
