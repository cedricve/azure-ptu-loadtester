from urllib.parse import parse_qs, urlsplit

import pytest

from azure_ptu_loadtester.config import ConfigError, load_endpoints


CONFIG = """
[[endpoints]]
name = "first"
url = "https://first.example/chat/completions?existing=value&api-version=old"
api_key_env = "FIRST_KEY"
model = "model-a"
api_version = "2025-01-01"

[[endpoints]]
name = "second"
url = "https://second.example/chat/completions"
api_key_env = "SECOND_KEY"
model = "model-b"
api_version = "2025-02-02"
"""


def test_loads_two_endpoints_and_replaces_api_version(tmp_path):
    config_path = tmp_path / "loadtest.toml"
    config_path.write_text(CONFIG)

    first, second = load_endpoints(
        config_path,
        {"FIRST_KEY": "secret-a", "SECOND_KEY": "secret-b"},
    )

    assert first.api_key == "secret-a"
    assert first.public_dict() == {
        "name": "first",
        "url": "https://first.example/chat/completions?existing=value&api-version=old",
        "model": "model-a",
        "api_version": "2025-01-01",
        "token_limit_parameter": "max_tokens",
    }
    assert parse_qs(urlsplit(first.request_url).query) == {
        "existing": ["value"],
        "api-version": ["2025-01-01"],
    }
    assert parse_qs(urlsplit(second.request_url).query) == {
        "api-version": ["2025-02-02"]
    }


def test_supports_v1_endpoint_without_api_version(tmp_path):
    config_path = tmp_path / "loadtest.toml"
    config_path.write_text(
        """
[[endpoints]]
name = "paygo"
url = "https://example.openai.azure.com/openai/v1/chat/completions"
api_key_env = "AZURE_OPENAI_API_KEY"
model = "gpt-5.5"
token_limit_parameter = "max_completion_tokens"

[[endpoints]]
name = "ptu"
url = "https://example.openai.azure.com/openai/v1/chat/completions"
api_key_env = "AZURE_OPENAI_API_KEY"
model = "gpt-5.5-2"
token_limit_parameter = "max_completion_tokens"
"""
    )

    first, second = load_endpoints(
        config_path,
        {"AZURE_OPENAI_API_KEY": "secret"},
    )

    assert first.request_url == first.url
    assert first.api_version is None
    assert first.token_limit_parameter == "max_completion_tokens"
    assert second.model == "gpt-5.5-2"


def test_rejects_missing_key_environment_variable(tmp_path):
    config_path = tmp_path / "loadtest.toml"
    config_path.write_text(CONFIG)

    with pytest.raises(ConfigError, match="SECOND_KEY"):
        load_endpoints(config_path, {"FIRST_KEY": "secret-a"})