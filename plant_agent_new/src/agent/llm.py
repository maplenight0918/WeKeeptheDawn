"""The two reasoning calls use standard-library HTTP only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import ROOT
from src.retrieval.embedder import ProviderError, post_json

PROVIDER = "openrouter"
MODEL = "anthropic/claude-sonnet-4.5"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def parse_json(text):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char == "{":
            try:
                result, _ = decoder.raw_decode(text[index:])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
    raise ProviderError("LLM 未回傳有效 JSON 物件。")


def complete(system, user, max_tokens=None):
    payload = {"model": MODEL, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user},
    ]}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    result = post_json(ENDPOINT, payload, timeout=120)
    try:
        return parse_json(result["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("LLM 回應格式無效。") from exc
