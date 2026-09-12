"""Query embeddings; corpus and query model must always match."""
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import ROOT

PROVIDER = "openrouter"
MODEL = "voyageai/voyage-4"
DIMENSIONS = 1024
ENDPOINT = "https://openrouter.ai/api/v1/embeddings"


class ProviderError(RuntimeError):
    pass


def post_json(endpoint, payload, timeout=30):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or "..." in key:
        raise ProviderError("請在 .env 設定有效的 OPENROUTER_API_KEY。")
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ProviderError(f"OpenRouter HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise ProviderError("OpenRouter 連線失敗或逾時。") from exc


@lru_cache(maxsize=128)
def embed(query: str):
    result = post_json(ENDPOINT, {"model": MODEL, "input": [query], "dimensions": DIMENSIONS})
    try:
        vector = np.asarray(result["data"][0]["embedding"], dtype=np.float32)
        norm = np.linalg.norm(vector)
        if vector.shape != (DIMENSIONS,) or not np.isfinite(vector).all() or norm == 0:
            raise ValueError("Invalid embedding")
        vector = vector / norm
        vector.flags.writeable = False
        return vector
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError("OpenRouter 回傳的 embedding 格式無效。") from exc
