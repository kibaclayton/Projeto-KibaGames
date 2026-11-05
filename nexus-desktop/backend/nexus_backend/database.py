from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import unicodedata

SCHEMA_VERSION = 7


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c))


def data_directory() -> Path:
    if override := os.environ.get('NEXUS_DATA_DIR'):
        return Path(override).resolve()
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
    return root / 'NexusWolfs'


SCHEMA = """
CREATE TABLE usuarios (
 id INTEGER PRIMARY KEY, nome TEXT NOT NULL, nome_chave TEXT NOT NULL UNIQUE,
 senha_hash TEXT NOT NULL, avatar_id TEXT REFERENCES imagens(id),
 criado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE imagens (
 id TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
 tipo TEXT NOT NULL CHECK(tipo IN ('capa','avatar','colecao')),
 largura INTEGER NOT NULL, altura INTEGER NOT NULL, bytes INTEGER NOT NULL
);
CREATE INDEX idx_imagens_usuario ON imagens(usuario_id);
CREATE TABLE colecoes (
 id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
 nome TEXT NOT NULL, nome_chave TEXT NOT NULL, capa_id TEXT REFERENCES imagens(id),
 UNIQUE(usuario_id,nome_chave), UNIQUE(id,usuario_id)
);
CREATE TABLE jogos (
 id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
 nome TEXT NOT NULL, nome_chave TEXT NOT NULL, plataforma TEXT NOT NULL,
 progresso INTEGER NOT NULL DEFAULT 0 CHECK(progresso BETWEEN 0 AND 100),
 capa_id TEXT REFERENCES imagens(id), data_inicio TEXT, data_termino TEXT,
 grupo TEXT NOT NULL DEFAULT '', ordem INTEGER NOT NULL DEFAULT 1 CHECK(ordem BETWEEN 1 AND 9999),
 favorito INTEGER NOT NULL DEFAULT 0 CHECK(favorito IN (0,1)),
 colecao_id INTEGER, trofeus_obtidos INTEGER NOT NULL DEFAULT 0,
 trofeus_total INTEGER NOT NULL DEFAULT 0,
 status_avancado TEXT NOT NULL DEFAULT '', notas TEXT NOT NULL DEFAULT '',
 cronograma TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(cronograma)),
 genero TEXT NOT NULL DEFAULT '', minutos_jogados INTEGER NOT NULL DEFAULT 0 CHECK(minutos_jogados >= 0),
 atualizado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 CHECK(trofeus_obtidos >= 0 AND trofeus_obtidos <= trofeus_total AND trofeus_total <= 1000000),
 CHECK(data_inicio IS NULL OR data_termino IS NULL OR data_termino >= data_inicio),
 FOREIGN KEY(colecao_id,usuario_id) REFERENCES colecoes(id,usuario_id)
);
CREATE INDEX idx_jogos_usuario_nome ON jogos(usuario_id,nome_chave,id);
CREATE INDEX idx_jogos_usuario_progresso ON jogos(usuario_id,progresso DESC,id);
CREATE INDEX idx_jogos_colecao ON jogos(usuario_id,colecao_id,ordem,id);
CREATE INDEX idx_jogos_favoritos ON jogos(usuario_id,favorito);
CREATE TABLE migracoes (origem TEXT PRIMARY KEY, relatorio TEXT NOT NULL, criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
PRAGMA user_version = 1;
"""

# Migrações incrementais: cada entrada leva o banco da versão anterior para a sua. Nunca remova colunas nem dados.
MIGRATIONS = {
    2: """
CREATE TABLE aparelhos (
 id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL UNIQUE, nome TEXT NOT NULL DEFAULT '',
 criado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 ultimo_uso TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 expira TEXT NOT NULL
);
CREATE INDEX idx_aparelhos_usuario ON aparelhos(usuario_id);
PRAGMA user_version = 2;
""",
    3: """
ALTER TABLE aparelhos ADD COLUMN hash_anterior TEXT;
ALTER TABLE aparelhos ADD COLUMN rotacionado TEXT;
PRAGMA user_version = 3;
""",
    # Ficha do jogo vinda de fontes externas (Steam, Wikidata). Todos opcionais; data de lançamento é da obra, nunca da
    # jornada pessoal (data_inicio/data_termino continuam sendo quando a pessoa começou e terminou de jogar).
    4: """
ALTER TABLE jogos ADD COLUMN data_lancamento TEXT;
ALTER TABLE jogos ADD COLUMN desenvolvedor TEXT NOT NULL DEFAULT '';
ALTER TABLE jogos ADD COLUMN publicadora TEXT NOT NULL DEFAULT '';
ALTER TABLE jogos ADD COLUMN descricao TEXT NOT NULL DEFAULT '';
ALTER TABLE jogos ADD COLUMN fonte_externa TEXT NOT NULL DEFAULT '';
ALTER TABLE jogos ADD COLUMN id_externo TEXT NOT NULL DEFAULT '';
ALTER TABLE jogos ADD COLUMN url_origem TEXT NOT NULL DEFAULT '';
CREATE INDEX idx_jogos_externo ON jogos(usuario_id,fonte_externa,id_externo);
PRAGMA user_version = 4;
""",
    # Jornada em andamento, ordem manual da biblioteca, origem do total de troféus, preferências visuais por perfil e
    # galeria de até cinco avatares. Tudo opcional; a posição manual nasce igual ao id para manter a ordem de cadastro.
    5: """
ALTER TABLE jogos ADD COLUMN ainda_jogando INTEGER NOT NULL DEFAULT 0 CHECK(ainda_jogando IN (0,1));
ALTER TABLE jogos ADD COLUMN posicao INTEGER;
ALTER TABLE jogos ADD COLUMN trofeus_fonte TEXT NOT NULL DEFAULT '';
ALTER TABLE jogos ADD COLUMN trofeus_escopo TEXT NOT NULL DEFAULT '';
ALTER TABLE jogos ADD COLUMN trofeus_consultado_em TEXT;
ALTER TABLE usuarios ADD COLUMN preferencias TEXT NOT NULL DEFAULT '{}';
CREATE TABLE avatares (
 usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
 posicao INTEGER NOT NULL CHECK(posicao BETWEEN 1 AND 5),
 imagem_id TEXT NOT NULL REFERENCES imagens(id),
 criado TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 PRIMARY KEY(usuario_id, posicao)
);
UPDATE jogos SET posicao = id WHERE posicao IS NULL;
INSERT INTO avatares(usuario_id, posicao, imagem_id) SELECT id, 1, avatar_id FROM usuarios WHERE avatar_id IS NOT NULL;
CREATE INDEX idx_jogos_posicao ON jogos(usuario_id,posicao);
PRAGMA user_version = 5;
""",
    # Ficha completa vinda das fontes (requisitos, idiomas, classificação indicativa, tempo de jogo, categorias), em JSON
    # fechado validado pelo modelo Ficha; editável e nunca sobrescreve o que a pessoa digitou.
    6: """
ALTER TABLE jogos ADD COLUMN ficha TEXT NOT NULL DEFAULT '{}';
PRAGMA user_version = 6;
""",
    # Página do jogo: imagem de fundo (captura/arte da fonte, tipo 'fundo') e nota pessoal de 1 a 5 estrelas. A restrição
    # CHECK de `imagens.tipo` exige recriar a tabela; a migração roda com chaves estrangeiras desligadas (ver initialize).
    7: """
CREATE TABLE imagens_v7 (
 id TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
 tipo TEXT NOT NULL CHECK(tipo IN ('capa','avatar','colecao','fundo')),
 largura INTEGER NOT NULL, altura INTEGER NOT NULL, bytes INTEGER NOT NULL
);
INSERT INTO imagens_v7(id,usuario_id,tipo,largura,altura,bytes) SELECT id,usuario_id,tipo,largura,altura,bytes FROM imagens;
DROP TABLE imagens;
ALTER TABLE imagens_v7 RENAME TO imagens;
CREATE INDEX idx_imagens_usuario ON imagens(usuario_id);
ALTER TABLE jogos ADD COLUMN fundo_id TEXT REFERENCES imagens(id);
ALTER TABLE jogos ADD COLUMN nota INTEGER CHECK(nota BETWEEN 1 AND 5);
PRAGMA user_version = 7;
""",
}
# Migrações que recriam tabelas referenciadas: precisam de PRAGMA foreign_keys=OFF fora da transação; a verificação
# foreign_key_check roda logo depois e qualquer pendência interrompe a abertura.
MIGRATIONS_WITHOUT_FK = {7}


class Database:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / 'nexus.sqlite3'

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError('Banco criado por uma versão mais nova do Nexus.')
            conn.execute('PRAGMA journal_mode=WAL')
            if version == 0:
                conn.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
                version = 1
            for target in range(version + 1, SCHEMA_VERSION + 1):
                if target in MIGRATIONS_WITHOUT_FK:
                    conn.execute('PRAGMA foreign_keys=OFF')
                    try:
                        conn.executescript('BEGIN IMMEDIATE;\n' + MIGRATIONS[target] + '\nCOMMIT;')
                        problems = conn.execute('PRAGMA foreign_key_check').fetchall()
                        if problems:
                            raise RuntimeError(f'Migração {target} deixou referências pendentes: {problems[:3]}')
                    finally:
                        conn.execute('PRAGMA foreign_keys=ON')
                else:
                    conn.executescript('BEGIN IMMEDIATE;\n' + MIGRATIONS[target] + '\nCOMMIT;')

