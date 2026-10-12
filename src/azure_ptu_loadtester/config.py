from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class ConfigError(ValueError):
    """Raised when the endpoint configuration is invalid."""


type TokenLimitParameter = Literal["max_tokens", "max_completion_tokens"]


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    name: str
    url: str
    api_key: str = field(repr=False)
    model: str
    api_version: str | None = None
    token_limit_parameter: TokenLimitParameter = "max_tokens"

    @property
    def request_url(self) -> str:
        if self.api_version is None:
            return self.url

        parts = urlsplit(self.url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["api-version"] = self.api_version
        return urlunsplit(parts._replace(query=urlencode(query)))

    def public_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "url": self.url,
            "model": self.model,
            "api_version": self.api_version,
            "token_limit_parameter": self.token_limit_parameter,
        }


def load_endpoints(
    path: str | Path,
    environ: Mapping[str, str] | None = None,
) -> tuple[EndpointConfig, EndpointConfig]:
    config_path = Path(path)
    environment = os.environ if environ is None else environ

    try:
        with config_path.open("rb") as config_file:
            document = tomllib.load(config_file)
    except FileNotFoundError as error:
        raise ConfigError(f"Configuration file not found: {config_path}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"Invalid TOML in {config_path}: {error}") from error

    entries = document.get("endpoints")
    if not isinstance(entries, list) or len(entries) != 2:
        raise ConfigError("Configuration must contain exactly two [[endpoints]] entries")

    endpoints = tuple(
        _parse_endpoint(entry, index, environment) for index, entry in enumerate(entries, 1)
    )
    if endpoints[0].name == endpoints[1].name:
        raise ConfigError("Endpoint names must be unique")
    return endpoints


def _parse_endpoint(
    entry: object,
    index: int,
    environ: Mapping[str, str],
) -> EndpointConfig:
    if not isinstance(entry, dict):
        raise ConfigError(f"Endpoint {index} must be a TOML table")

    required = ("name", "url", "api_key_env", "model")
    values: dict[str, str] = {}
    for field in required:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"Endpoint {index} requires a non-empty '{field}' value")
        values[field] = value.strip()

    parsed_url = urlsplit(values["url"])
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ConfigError(f"Endpoint '{values['name']}' has an invalid URL")

    api_key = environ.get(values["api_key_env"])
    if not api_key:
        raise ConfigError(
            f"Environment variable {values['api_key_env']} is not set "
            f"for endpoint '{values['name']}'"
        )

    api_version = entry.get("api_version")
    if api_version is not None:
        if not isinstance(api_version, str) or not api_version.strip():
            raise ConfigError(
                f"Endpoint {index} 'api_version' must be a non-empty string"
            )
        api_version = api_version.strip()

    raw_token_parameter = entry.get("token_limit_parameter", "max_tokens")
    if raw_token_parameter == "max_tokens":
        token_limit_parameter: TokenLimitParameter = "max_tokens"
    elif raw_token_parameter == "max_completion_tokens":
        token_limit_parameter = "max_completion_tokens"
    else:
        raise ConfigError(
            f"Endpoint {index} 'token_limit_parameter' must be "
            "'max_tokens' or 'max_completion_tokens'"
        )

    return EndpointConfig(
        name=values["name"],
        url=values["url"],
        api_key=api_key,
        model=values["model"],
        api_version=api_version,
        token_limit_parameter=token_limit_parameter,
    )