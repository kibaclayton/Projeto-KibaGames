from nexus_backend.platforms import clean_genre, nexus_platforms, normalize_genre, normalize_platform, suggest_genre


def test_platform_names_from_stores_and_wikidata_map_to_nexus_options():
    assert normalize_platform('Windows') == 'PC' and normalize_platform('PC (Windows)') == 'PC' and normalize_platform('macOS') == 'PC'
    assert normalize_platform('Linux') == 'PC' and normalize_platform('Steam Deck') == 'PC'
    assert normalize_platform('PlayStation 5') == 'PS5' and normalize_platform('PS5') == 'PS5'
    assert normalize_platform('PlayStation 4') == 'PS4' and normalize_platform('PlayStation 4 Pro') == 'PS4'
    assert normalize_platform('Xbox One') == 'Xbox' and normalize_platform('Xbox Series X e Series S') == 'Xbox' and normalize_platform('Xbox 360') == 'Xbox'
    assert normalize_platform('Nintendo Switch') == 'Switch' and normalize_platform('Nintendo Switch 2') == 'Switch'
    assert normalize_platform('PlayStation 3') is None, 'sem opção equivalente no Nexus, nada é sugerido (nunca "Outro" sozinho)'
    assert normalize_platform('') is None and normalize_platform('Android') is None


def test_platform_lists_keep_order_and_drop_repeats_and_unknowns():
    assert nexus_platforms(['Windows', 'macOS', 'Linux']) == ['PC']
    assert nexus_platforms(['PlayStation 5', 'Xbox Series X e Series S', 'Windows', 'PlayStation 4', 'Nintendo Switch', 'Stadia']) == ['PS5', 'Xbox', 'PC', 'PS4', 'Switch']
    assert nexus_platforms([]) == []


def test_genres_from_steam_and_wikidata_become_nexus_filters_or_clean_names():
    assert normalize_genre('Ação') == 'Ação' and normalize_genre('Action') == 'Ação'
    assert normalize_genre('RPG') == 'RPG' and normalize_genre('role-playing video game') == 'RPG' and normalize_genre('jogo eletrônico de interpretação de papéis') == 'RPG'
    assert normalize_genre('first-person shooter') == 'FPS' and normalize_genre('tiro em primeira pessoa') == 'FPS'
    assert normalize_genre('survival horror') == 'Terror' and normalize_genre('Estratégia') == 'Estratégia' and normalize_genre('Adventure') == 'Aventura'
    assert clean_genre('jogo eletrônico de plataforma') == 'Plataforma' and clean_genre('metroidvania') == 'Metroidvania'
    assert clean_genre('puzzle video game') == 'Puzzle' and clean_genre('') == ''


def test_suggested_genre_prefers_a_nexus_filter_then_the_first_genre():
    assert suggest_genre(['Indie', 'Aventura', 'Ação']) == 'Aventura'
    assert suggest_genre(['metroidvania', 'jogo eletrônico de ação-aventura']) == 'Ação'
    assert suggest_genre(['jogo eletrônico de plataforma']) == 'Plataforma'
    assert suggest_genre([]) == '' and suggest_genre(['', None]) == ''
