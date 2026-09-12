import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import dotenv_values
from app.world_rules import ROOT, RULES, digest

class ConfigurationError(ValueError):
    pass

@dataclass
class Settings:
    agent_mode: str = 'mock'
    parameter_profile: str = 'world_v0_12'
    world_rules_version: str = '0.12'
    world_rules_path: str = './data/world_rules_v0.12.json'
    retrieval_mode: str = 'dense'
    retrieval_fallback: str = 'bm25'
    retrieval_top_k: int = 5
    index_dir: str = './data/index'
    embedding_provider: str = 'openrouter'
    embedding_model: str = 'voyageai/voyage-4'
    embedding_base_url: str = 'https://openrouter.ai/api/v1'
    embedding_api_key: str = field(default='', repr=False)
    embedding_dimensions: int = 1024
    embedding_input_type_policy: str = 'unspecified'
    embedding_batch_size: int = 16
    embedding_timeout_seconds: float = 10
    llm_provider: str = 'openai_compatible'
    llm_base_url: str = 'https://api.openai.com/v1'
    llm_model: str = 'gpt-6-astra'
    llm_api_key: str = field(default='', repr=False)
    llm_timeout_seconds: float = 30
    analysis_timeout_seconds: float = 45
    max_llm_calls: int = 4
    max_tool_calls: int = 8
    human_agent_url: str = 'http://127.0.0.1:8000'
    brain_client_timeout_seconds: float = 60

    @classmethod
    def load(cls):
        values = {**dotenv_values(ROOT / '.env'), **os.environ}
        defaults = cls()
        kwargs = {}
        for key in cls.__dataclass_fields__:
            if key.upper() in values:
                try:
                    kwargs[key] = type(getattr(defaults, key))(values[key.upper()] or '')
                except (TypeError, ValueError):
                    raise ConfigurationError('Invalid setting: ' + key.upper()) from None
        result = cls(**kwargs)
        result.validate()
        return result

    def path(self, value):
        path = Path(value)
        return path if path.is_absolute() else ROOT / path

    def validate(self):
        if self.parameter_profile != 'world_v0_12':
            raise ConfigurationError('PARAMETER_PROFILE must migrate to world_v0_12; scientific/demo unsupported')
        if self.world_rules_version != '0.12':
            raise ConfigurationError('WORLD_RULES_VERSION must be 0.12')
        import json
        try:
            if digest(json.loads(self.path(self.world_rules_path).read_text(encoding='utf-8'))) != digest(RULES):
                raise ValueError()
        except (OSError, ValueError):
            raise ConfigurationError('WORLD_RULES_PATH content does not match world_v0_12 rules hash') from None
        for key, allowed in [('agent_mode', {'mock','live'}), ('retrieval_mode', {'dense','bm25'}), ('retrieval_fallback', {'bm25','none'}), ('llm_provider', {'openrouter','openai_compatible'}), ('embedding_provider', {'openrouter','voyage'})]:
            if getattr(self, key) not in allowed:
                raise ConfigurationError('Unsupported setting: ' + key.upper())
        policy = 'query_document' if self.embedding_provider == 'voyage' else 'unspecified'
        if self.embedding_input_type_policy != policy:
            raise ConfigurationError('EMBEDDING_INPUT_TYPE_POLICY incompatible with EMBEDDING_PROVIDER')
        for key in ['retrieval_top_k','embedding_dimensions','embedding_batch_size','embedding_timeout_seconds','llm_timeout_seconds','analysis_timeout_seconds','max_llm_calls','max_tool_calls','brain_client_timeout_seconds']:
            import math
            if not math.isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ConfigurationError('Invalid setting: ' + key.upper())
        self.max_llm_calls = min(self.max_llm_calls, 4)
        self.max_tool_calls = min(self.max_tool_calls, 8)
        self.analysis_timeout_seconds = min(self.analysis_timeout_seconds, 45)

    def missing(self):
        return [k.upper() for k in ['llm_api_key','llm_model','llm_base_url','embedding_api_key','embedding_model','embedding_base_url'] if not getattr(self,k)]
