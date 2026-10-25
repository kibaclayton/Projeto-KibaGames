import io
from PIL import Image, ImageOps, ImageDraw


def highlights(games):
    return sorted((g for g in games if 0 < g['progresso'] < 100 and
                   g.get('status_avancado') not in ('Concluído', 'Abandonado', 'Pausado', 'Na fila')),
                  key=lambda g: (-g['progresso'], g['nome'].casefold(), g['id']))


def trophy_values(obtained, total):
    try:
        obtained, total = int(obtained), int(total)
    except (TypeError, ValueError):
        raise ValueError('Os troféus devem ser números inteiros.')
    if not 0 <= obtained <= total <= 1000000:
        raise ValueError('Use valores de 0 a 1.000.000. Obtidos não pode superar o total.')
    return obtained, total, 100 * obtained / total if total else 0


def artwork(data, size, circle=False):
    background = Image.new('RGB', size, '#151b24')
    if data:
        try:
            with Image.open(io.BytesIO(data)) as source:
                picture = ImageOps.fit(source.convert('RGB'), size) if circle else ImageOps.pad(source.convert('RGB'), size, color='#151b24')
            if circle:
                mask = Image.new('L', size)
                ImageDraw.Draw(mask).ellipse((0, 0, size[0]-1, size[1]-1), fill=255)
                background.paste(picture, (0, 0), mask)
            else:
                background = picture
        except (OSError, ValueError):
            pass
    else:
        draw = ImageDraw.Draw(background)
        w, h = size
        draw.rounded_rectangle((w*.22,h*.33,w*.78,h*.67), radius=12, outline='#709332', width=3)
        draw.line((w*.3,h*.5,w*.44,h*.5), fill='#bcff36', width=3)
        draw.line((w*.37,h*.43,w*.37,h*.57), fill='#bcff36', width=3)
        draw.ellipse((w*.61,h*.44,w*.67,h*.50), fill='#bcff36')
    return background


def mosaic(games, size=150):
    picture = Image.new('RGB', (size,size), '#151b24')
    for index, game in enumerate(games[:4]):
        picture.paste(artwork(game.get('capa'), (size//2-2,size//2-2)),
                      ((index%2)*(size//2), (index//2)*(size//2)))
    return picture
