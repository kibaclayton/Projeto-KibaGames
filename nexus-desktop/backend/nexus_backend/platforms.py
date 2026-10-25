"""Normalização de plataformas e gêneros vindos de fontes externas para as opções do Nexus.

Regras centrais e testáveis: a interface recebe tanto os nomes originais quanto a opção equivalente do Nexus e nunca
precisa adivinhar. Quando um nome não casa com nenhuma regra, ele fica fora da sugestão (nunca vira "Outro" sozinho).
"""
import re

NEXUS_PLATFORMS = ('PC', 'PS5', 'PS4', 'Xbox', 'Switch', 'Outro')
PLATFORM_RULES = (
    (re.compile(r'playstation\s*5|\bps5\b', re.I), 'PS5'),
    (re.compile(r'playstation\s*4|\bps4\b', re.I), 'PS4'),
    (re.compile(r'\bxbox', re.I), 'Xbox'),
    (re.compile(r'nintendo\s*switch|\bswitch\b', re.I), 'Switch'),
    (re.compile(r'windows|\bpc\b|mac\s*os|\bmac\b|\blinux\b|steamos|steam deck', re.I), 'PC'),
)
NEXUS_GENRES = ('RPG', 'Ação', 'FPS', 'Aventura', 'Terror', 'Estratégia')
GENRE_RULES = (
    (re.compile(r'\brpg\b|role[- ]playing|interpreta[çc][ãa]o de pap[ée]is', re.I), 'RPG'),
    (re.compile(r'\bfps\b|first[- ]person shooter|tiro em primeira pessoa|\bshooter\b|\btiro\b', re.I), 'FPS'),
    (re.compile(r'terror|horror', re.I), 'Terror'),
    (re.compile(r'estrat[ée]gia|strategy', re.I), 'Estratégia'),
    (re.compile(r'a[çc][ãa]o|\baction\b', re.I), 'Ação'),
    (re.compile(r'aventura|adventure', re.I), 'Aventura'),
)
GENRE_NOISE = re.compile(r'^(jogo eletr[ôo]nico de |jogo de |videojogo de |video ?game de |video ?game |videojogo )|( \(g[êe]nero\)| video ?game| game)$', re.I)


def normalize_platform(name: str) -> str | None:
    """Nome de plataforma de uma fonte → opção do Nexus, ou None quando não há correspondência clara."""
    for pattern, option in PLATFORM_RULES:
        if pattern.search(name or ''):
            return option
    return None


def nexus_platforms(names) -> list[str]:
    """Opções do Nexus para uma lista de plataformas, sem repetição e na ordem em que aparecem."""
    result = []
    for name in names:
        option = normalize_platform(name)
        if option and option not in result:
            result.append(option)
    return result


def clean_genre(name: str) -> str:
    """Remove ruído como "jogo eletrônico de" e devolve o gênero com inicial maiúscula."""
    text = re.sub(r'\s+', ' ', (name or '').strip())
    text = GENRE_NOISE.sub('', text).strip(' -')
    return text[:1].upper() + text[1:] if text else ''


def normalize_genre(name: str) -> str:
    for pattern, option in GENRE_RULES:
        if pattern.search(name or ''):
            return option
    return clean_genre(name)


def suggest_genre(names) -> str:
    """Primeiro gênero que coincide com um filtro do Nexus; senão o primeiro gênero limpo; vazio se não houver."""
    cleaned = [normalize_genre(name) for name in names if name]
    for genre in cleaned:
        if genre in NEXUS_GENRES:
            return genre
    return cleaned[0][:80] if cleaned else ''
