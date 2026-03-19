"""modelos Pydantic e regras de validacao dos payloads da API."""

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _validate_resource_id(value: str, *, field_name: str) -> str:
    if not RESOURCE_ID_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} inválido. Use apenas letras, números, '_' e '-', até 64 caracteres."
        )
    return value


class ApiModel(BaseModel):
    """Base comum para payloads da API com trim automatico de strings."""

    model_config = ConfigDict(str_strip_whitespace=True)


class MusicRequest(ApiModel):
    """Payload para requisicao de busca/tocar musica."""

    search: str = Field(min_length=1, max_length=2048)

    @field_validator("search")
    @classmethod
    def validate_search(cls, value: str) -> str:
        """Valida search."""
        if "\x00" in value:
            raise ValueError("Busca inválida.")
        return value


class VolumeRequest(ApiModel):
    """Payload para ajuste de volume do player."""

    level: float = Field(ge=0.0, le=1.5)


class PlaylistUploadRequest(ApiModel):
    """Payload para upload de playlist via API."""

    file: str = Field(min_length=1, max_length=2_000_000)
    filename: str = Field(min_length=1, max_length=128)
    encoding: Literal["plain", "base64"] = "plain"


class RadioRequest(ApiModel):
    """Payload para cadastro de nova radio personalizada."""

    name: str = Field(min_length=2, max_length=80)
    url: str = Field(min_length=10, max_length=2048)
    location: str = Field(default="Desconhecido", max_length=120)
    description: str = Field(default="Rádio personalizada", max_length=240)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Valida url."""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL inválida. Use http(s)://...")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Valida name."""
        if len(value.strip(" .-_")) < 2:
            raise ValueError("Nome da rádio inválido.")
        return value


class RadioRemoveRequest(ApiModel):
    """Payload para remocao de radio pelo id."""

    radio_id: str = Field(min_length=1, max_length=64)

    @field_validator("radio_id")
    @classmethod
    def validate_radio_id(cls, value: str) -> str:
        """Valida radio id."""
        return _validate_resource_id(value, field_name="radio_id")


class RadioPlayRequest(ApiModel):
    """Payload para tocar radio por id no servidor."""

    radio_id: str = Field(min_length=1, max_length=64)
    guild_id: PositiveInt | None = None

    @field_validator("radio_id")
    @classmethod
    def validate_radio_id(cls, value: str) -> str:
        """Valida radio id."""
        return _validate_resource_id(value, field_name="radio_id")


class SoundboardPlayRequest(ApiModel):
    """Payload para tocar efeito da soundboard."""

    guild_id: PositiveInt
    sfx_id: str = Field(min_length=1, max_length=64)

    @field_validator("sfx_id")
    @classmethod
    def validate_sfx_id(cls, value: str) -> str:
        """Valida sfx id."""
        return _validate_resource_id(value, field_name="sfx_id")


class SoundboardFavoriteRequest(ApiModel):
    """Payload para favoritar ou desfavoritar um efeito."""

    sfx_id: str = Field(min_length=1, max_length=64)
    favorite: bool

    @field_validator("sfx_id")
    @classmethod
    def validate_sfx_id(cls, value: str) -> str:
        """Valida sfx id."""
        return _validate_resource_id(value, field_name="sfx_id")


class SoundboardVolumeRequest(ApiModel):
    """Payload para ajustar volume de um efeito da soundboard."""

    sfx_id: str = Field(min_length=1, max_length=64)
    volume: float = Field(ge=0.0, le=2.0)

    @field_validator("sfx_id")
    @classmethod
    def validate_sfx_id(cls, value: str) -> str:
        """Valida sfx id."""
        return _validate_resource_id(value, field_name="sfx_id")


class LanguageRequest(ApiModel):
    """Payload para definir idioma da aplicacao."""

    language: Literal["pt", "en"]
