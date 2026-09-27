from datetime import date
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


class PasswordChange(Model):
    senha_atual: str = Field(min_length=1, max_length=256)
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

    @field_validator('nome', 'plataforma')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Campo vazio.')
        return value.strip()

    @field_validator('cronograma')
    @classmethod
    def schedule(cls, value):
        for day in value:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError('Use datas ISO YYYY-MM-DD no cronograma.')
        return value

    @model_validator(mode='after')
    def consistency(self):
        if self.trofeus_obtidos > self.trofeus_total:
            raise ValueError('Obtidos não pode superar o total de troféus.')
        if self.data_inicio and self.data_termino and self.data_termino < self.data_inicio:
            raise ValueError('Término anterior ao início.')
        return self


class Crop(Model):
    """Pixels of the EXIF-oriented source, matching react-easy-crop croppedAreaPixels."""
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class RemoteImage(Model):
    url: str = Field(min_length=8, max_length=2048)
    tipo: Literal['capa', 'avatar', 'colecao'] = 'capa'
    recorte: Crop | None = None
