from datetime import date
import re
from urllib.parse import urlsplit
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProfileCreate(Model):
    nome: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=8, max_length=256)

    @field_validator('nome')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Informe um nome.')
        return value.strip()


class Login(Model):
    perfil_id: int = Field(gt=0)
    senha: str = Field(min_length=1, max_length=256)
    lembrar: bool = False
    aparelho: str = Field(default='', max_length=80)


class DeviceToken(Model):
    token: str = Field(min_length=20, max_length=128)


class PasswordChange(Model):
    senha_atual: str = Field(min_length=1, max_length=256)
    nova_senha: str = Field(min_length=8, max_length=256)
    confirmar_senha: str = Field(min_length=8, max_length=256)

    @model_validator(mode='after')
    def confirm(self):
        if self.nova_senha != self.confirmar_senha:
            raise ValueError('A confirmação da senha não confere.')
        return self


class PasswordReset(Model):
    """Esqueci a senha: só a senha nova, sem a atual; o endpoint restringe a origem a este computador."""
    nova_senha: str = Field(min_length=8, max_length=256)
    confirmar_senha: str = Field(min_length=8, max_length=256)

    @model_validator(mode='after')
    def confirm(self):
        if self.nova_senha != self.confirmar_senha:
            raise ValueError('A confirmação da senha não confere.')
        return self


class ImageRef(Model):
    imagem_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class CollectionInput(Model):
    nome: str = Field(min_length=1, max_length=150)
    capa_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @field_validator('nome')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Informe um nome.')
        return value.strip()


class Ficha(Model):
    """Ficha completa da obra, vinda das fontes ou digitada: requisitos, idiomas, classificação indicativa, tempo de jogo e categorias.

    Tempos em minutos (história principal, com extras e 100%); só a IGDB os publica hoje. Nunca contém dados da jornada pessoal.
    """
    requisitos_minimos: str = Field(default='', max_length=3000)
    requisitos_recomendados: str = Field(default='', max_length=3000)
    idiomas: list[str] = Field(default_factory=list, max_length=60)
    classificacao: str = Field(default='', max_length=80)
    classificacao_detalhe: str = Field(default='', max_length=300)
    tempo_historia: int | None = Field(default=None, ge=0, le=100000)
    tempo_extras: int | None = Field(default=None, ge=0, le=100000)
    tempo_completo: int | None = Field(default=None, ge=0, le=100000)
    metacritic: int | None = Field(default=None, ge=0, le=100)
    categorias: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('idiomas', 'categorias')
    @classmethod
    def short_items(cls, value):
        result = []
        for item in value:
            text = ' '.join(str(item).split())[:60]
            if text and text not in result:
                result.append(text)
        return result

    @field_validator('requisitos_minimos', 'requisitos_recomendados', 'classificacao', 'classificacao_detalhe')
    @classmethod
    def clean_text(cls, value):
        return '\n'.join(' '.join(line.split()) for line in value.strip().splitlines() if line.strip())


class GameInput(Model):
    nome: str = Field(min_length=1, max_length=150)
    plataforma: str = Field(default='PC', min_length=1, max_length=30)
    progresso: int = Field(default=0, ge=0, le=100)
    capa_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    data_inicio: date | None = None
    data_termino: date | None = None
    grupo: str = Field(default='', max_length=150)
    ordem: int = Field(default=1, ge=1, le=9999)
    favorito: bool = False
    colecao_id: int | None = Field(default=None, gt=0)
    trofeus_obtidos: int = Field(default=0, ge=0, le=1000000)
    trofeus_total: int = Field(default=0, ge=0, le=1000000)
    status_avancado: str = Field(default='', max_length=40)
    notas: str = Field(default='', max_length=100000)
    cronograma: dict[str, Literal['single', 'range']] = Field(default_factory=dict, max_length=10000)
    genero: str = Field(default='', max_length=80)
    minutos_jogados: int = Field(default=0, ge=0, le=100000000)
    # Ficha vinda de fontes externas; opcional e editável. Nunca inclui progresso, status, notas, troféus ou datas pessoais.
    data_lancamento: date | None = None
    desenvolvedor: str = Field(default='', max_length=200)
    publicadora: str = Field(default='', max_length=200)
    descricao: str = Field(default='', max_length=4000)
    fonte_externa: Literal['', 'steam', 'wikipedia', 'igdb', 'retroachievements'] = ''
    id_externo: str = Field(default='', max_length=64, pattern=r'^[A-Za-z0-9:_-]*$')
    url_origem: str = Field(default='', max_length=2048)
    # Jornada em andamento: sem data de término enquanto marcado. Progresso não muda por causa disto.
    ainda_jogando: bool = False
    # Origem do total de troféus quando veio de uma fonte (ex.: 'steam', 'jogo base', data da consulta); vazio se manual.
    trofeus_fonte: str = Field(default='', max_length=40)
    trofeus_escopo: str = Field(default='', max_length=40)
    trofeus_consultado_em: str | None = Field(default=None, max_length=40)
    ficha: Ficha = Field(default_factory=Ficha)

    @field_validator('nome', 'plataforma')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Campo vazio.')
        return value.strip()

    @field_validator('url_origem')
    @classmethod
    def https_origin(cls, value):
        value = value.strip()
        if not value:
            return value
        parts = urlsplit(value)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443) or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError('A página de origem precisa ser um endereço HTTPS simples, sem credenciais ou porta alternativa.')
        return value

    @model_validator(mode='after')
    def external_identity(self):
        if bool(self.fonte_externa) != bool(self.id_externo):
            raise ValueError('Fonte externa e identificador externo precisam vir juntos.')
        return self

    @field_validator('cronograma')
    @classmethod
    def schedule(cls, value):
        for day in value:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError('Use datas ISO YYYY-MM-DD no cronograma.')
        return value

    @model_validator(mode='after')
    def consistency(self):
        if self.ainda_jogando:
            self.data_termino = None
        if self.trofeus_obtidos > self.trofeus_total:
            raise ValueError('Obtidos não pode superar o total de troféus.')
        if self.data_inicio and self.data_termino and self.data_termino < self.data_inicio:
            raise ValueError('Término anterior ao início.')
        return self


class OrderInput(Model):
    """Ordem manual da biblioteca: ids do próprio perfil, na sequência desejada."""
    ids: list[int] = Field(min_length=1, max_length=2000)


class AvatarSlot(Model):
    imagem_id: str = Field(pattern=r'^[a-f0-9]{64}$')


THEMES, MOTIONS, DENSITIES, ACCENTS = ('escuro', 'claro'), ('padrao', 'reduzida', 'desligada'), ('confortavel', 'compacta'), ('roxo', 'magenta', 'verde', 'azul')


class PreferencesInput(Model):
    """Preferências visuais por perfil; só valores aprovados do Design System, nunca CSS livre."""
    tema: Literal['escuro', 'claro'] = 'escuro'
    movimento: Literal['padrao', 'reduzida', 'desligada'] = 'padrao'
    densidade: Literal['confortavel', 'compacta'] = 'confortavel'
    destaque: Literal['roxo', 'magenta', 'verde', 'azul'] = 'roxo'


class Crop(Model):
    """Pixels of the EXIF-oriented source, matching react-easy-crop croppedAreaPixels."""
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class NetworkInput(Model):
    ativo: bool
    porta: int | None = Field(default=None, ge=1024, le=65535)


class CandidateRef(Model):
    """Resultado escolhido na busca: identidade do provedor, nunca uma URL livre vinda da interface."""
    fonte: Literal['steam', 'wikipedia', 'igdb']
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9:_-]+$')
    jogo_id: int | None = Field(default=None, gt=0)


TrophySource = Literal['steam', 'retroachievements']


class TrophySourceInput(Model):
    """Vínculo de uma fonte oficial de troféus: chave pessoal + identificação (SteamID64 ou usuário). Só deste computador."""
    api_key: str = Field(min_length=8, max_length=80)
    identificacao: str = Field(min_length=2, max_length=40)


class TrophyImportInput(Model):
    """Jogos da conta vinculada escolhidos para entrar na biblioteca; só identificadores que a própria fonte listou."""
    ids: list[str] = Field(min_length=1, max_length=50)
    modo: Literal['recentes', 'possuidos', 'todos'] = 'recentes'
    colecao_id: int | None = Field(default=None, gt=0)

    @field_validator('ids')
    @classmethod
    def numeric_ids(cls, value):
        if len(set(value)) != len(value) or any(not re.fullmatch(r'[0-9]{1,12}', item) for item in value):
            raise ValueError('Identificadores inválidos ou repetidos.')
        return value


class TrophySyncInput(Model):
    jogo_id: int | None = Field(default=None, gt=0)


class RemoteImage(Model):
    url: str = Field(min_length=8, max_length=2048)
    tipo: Literal['capa', 'avatar', 'colecao'] = 'capa'
    recorte: Crop | None = None
