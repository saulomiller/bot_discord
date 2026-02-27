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
    model_config = ConfigDict(str_strip_whitespace=True)


class MusicRequest(ApiModel):
    search: str = Field(min_length=1, max_length=2048)

    @field_validator("search")
    @classmethod
    def validate_search(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Busca inválida.")
        return value


class VolumeRequest(ApiModel):
    level: float = Field(ge=0.0, le=1.5)


class PlaylistUploadRequest(ApiModel):
    file: str = Field(min_length=1, max_length=2_000_000)
    filename: str = Field(min_length=1, max_length=128)
    encoding: Literal["plain", "base64"] = "plain"


class RadioRequest(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    url: str = Field(min_length=10, max_length=2048)
    location: str = Field(default="Desconhecido", max_length=120)
    description: str = Field(default="Rádio personalizada", max_length=240)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL inválida. Use http(s)://...")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if len(value.strip(" .-_")) < 2:
            raise ValueError("Nome da rádio inválido.")
        return value


class RadioRemoveRequest(ApiModel):
    radio_id: str = Field(min_length=1, max_length=64)

    @field_validator("radio_id")
    @classmethod
    def validate_radio_id(cls, value: str) -> str:
        return _validate_resource_id(value, field_name="radio_id")


class RadioPlayRequest(ApiModel):
    radio_id: str = Field(min_length=1, max_length=64)
    guild_id: PositiveInt | None = None

    @field_validator("radio_id")
    @classmethod
    def validate_radio_id(cls, value: str) -> str:
        return _validate_resource_id(value, field_name="radio_id")


class SoundboardPlayRequest(ApiModel):
    guild_id: PositiveInt
    sfx_id: str = Field(min_length=1, max_length=64)

    @field_validator("sfx_id")
    @classmethod
    def validate_sfx_id(cls, value: str) -> str:
        return _validate_resource_id(value, field_name="sfx_id")


class SoundboardFavoriteRequest(ApiModel):
    sfx_id: str = Field(min_length=1, max_length=64)
    favorite: bool

    @field_validator("sfx_id")
    @classmethod
    def validate_sfx_id(cls, value: str) -> str:
        return _validate_resource_id(value, field_name="sfx_id")


class SoundboardVolumeRequest(ApiModel):
    sfx_id: str = Field(min_length=1, max_length=64)
    volume: float = Field(ge=0.0, le=2.0)

    @field_validator("sfx_id")
    @classmethod
    def validate_sfx_id(cls, value: str) -> str:
        return _validate_resource_id(value, field_name="sfx_id")


class LanguageRequest(ApiModel):
    language: Literal["pt", "en"]
