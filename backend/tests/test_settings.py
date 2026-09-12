from __future__ import annotations

from pathlib import Path

import pytest

from backend.integration.settings import OpenAISettings, load_runtime_settings


def test_example_runtime_yaml_is_valid() -> None:
    path = Path(__file__).resolve().parents[2] / "config" / "runtime.example.yaml"
    settings = load_runtime_settings(path)
    assert settings.plan_source == "external"
    assert settings.openai.model is None
    assert settings.openai.api_key_env == "OPENAI_API_KEY"


def test_yaml_overrides_plan_source_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text("plan_source: external\n", encoding="utf-8")
    monkeypatch.setenv("GREENHOUSE_CONFIG", str(path))
    monkeypatch.setenv("PLAN_SOURCE", "mock")
    assert load_runtime_settings().plan_source == "external"


def test_model_and_key_environment_names_do_not_resolve_secret_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text("plan_source: external\nopenai:\n  api_key_env: TEAM_API_KEY\n  model_env: TEAM_MODEL\n", encoding="utf-8")
    monkeypatch.setenv("TEAM_API_KEY", "not-a-real-secret")
    monkeypatch.setenv("TEAM_MODEL", "teammate-selected-model")
    settings = load_runtime_settings(path)
    assert settings.openai.api_key_env == "TEAM_API_KEY"
    assert "not-a-real-secret" not in settings.model_dump_json()
    assert settings.openai.model is None


@pytest.mark.parametrize("contents", ["", "{}", "[]", "null", "plan_source: unexpected", "openai:\n  timeout_seconds: 0", "openai:\n  timeout_seconds: .nan"])
def test_empty_or_invalid_yaml_is_rejected(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        load_runtime_settings(path)


@pytest.mark.parametrize("contents", ["api_key: pasted-secret", "openai:\n  api_key: pasted-secret"])
def test_literal_api_key_rejected_without_echoing_it(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_runtime_settings(path)
    assert "api_key" in str(error.value)
    assert "pasted-secret" not in str(error.value)


def test_key_field_requires_an_environment_identifier() -> None:
    with pytest.raises(ValueError):
        OpenAISettings(api_key_env="not-an-env-name")
