"""Runtime integration configuration; credentials remain in environment variables."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class OpenAISettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    model: str | None = None
    model_env: str = Field(default="OPENAI_MODEL", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    api_key_env: str = Field(default="OPENAI_API_KEY", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)

    @field_validator("model")
    @classmethod
    def nonempty_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("model must be a nonempty name or null")
        return value

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("base_url must be an HTTP endpoint without embedded credentials")
        return value.rstrip("/")


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    plan_source: Literal["mock", "external"] = "mock"
    decision_timeout_seconds: float = Field(default=420, gt=0, allow_inf_nan=False)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)


def load_runtime_settings(path: str | Path | None = None) -> RuntimeSettings:
    """YAML overrides PLAN_SOURCE. No credential value is resolved or returned."""
    load_dotenv()
    selected = path if path is not None else os.environ.get("GREENHOUSE_CONFIG")
    if selected:
        try:
            data = yaml.safe_load(Path(selected).read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raise ValueError("Invalid YAML runtime configuration") from None
        if not isinstance(data, dict) or not data:
            raise ValueError("Runtime YAML must contain a nonempty mapping")
    else:
        data = {"plan_source": os.environ.get("PLAN_SOURCE", "mock")}
    try:
        return RuntimeSettings.model_validate(data)
    except ValidationError as exc:
        # Configuration errors never echo an accidentally pasted secret value.
        fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
        raise ValueError("Invalid runtime configuration fields: " + ", ".join(fields)) from None
