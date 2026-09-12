"""Retrieve evidence → select coefficients → compute → narrate."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import ROOT
from src.agent.llm import complete
from src.agent.prompts import SELECT_SYSTEM, NARRATE_SYSTEM
from src.models.coefficients import Coefficients
from src.models.greenhouse import simulate, sweep_ppfd
from src.retrieval.embedder import ProviderError
from src.retrieval.store import as_context

TUNABLE = ["biomass_rate", "transpiration", "wue", "growth_days", "led_power"]


def analyze(store, inp):
    p = inp.model_dump()
    coeffs = Coefficients(inp.crop)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {key: pool.submit(store.coefficient_evidence, key, inp.crop, 4) for key in TUNABLE}
        evidence = {key: future.result() for key, future in futures.items()}
    context = "\n\n".join(f"### 關於 {key}\n{as_context(evidence[key], 5000)}" for key in TUNABLE)
    user = ("目標情境：\n" + json.dumps(p, ensure_ascii=False) + "\n需要的係數與單位：\n" +
            json.dumps({key: coeffs.values[key]["unit"] for key in TUNABLE}, ensure_ascii=False) + "\n" + context)
    selected = complete(SELECT_SYSTEM, user)
    warnings = []
    for key in TUNABLE:
        choice = selected.get(key)
        if not isinstance(choice, dict) or choice.get("value") is None:
            continue
        value = choice["value"]
        if not coeffs.plausible(key, value):
            warnings.append(f"{key} 原選值 {value!r} 超出 corpus P25/3–P75×3，退回中位數 {coeffs[key]}。")
            continue
        source = choice.get("source", "")
        # A source must be one of the actual retrieved documents, not invented.
        sources = {f"{hit.source}:{hit.doc_id}" for hit in evidence[key]}
        if source not in sources:
            warnings.append(f"{key} 的來源無法對應檢索文獻，退回中位數 {coeffs[key]}。")
            continue
        coeffs.values[key].update(value=float(value), source=source, note=str(choice.get("note", "")))
    result = simulate(coeffs, inp)
    result["warnings"] = warnings + result["warnings"]
    ppfd = inp.ppfd
    levels = [ppfd, ppfd * 0.6, ppfd * 0.8, ppfd * 1.2]
    sweep = sweep_ppfd(coeffs, inp, [round(x) for x in levels])
    narration = complete(NARRATE_SYSTEM, json.dumps({"scenario": p, **result, "sweep": sweep}, ensure_ascii=False))
    if not (isinstance(narration.get("reasoning"), str) and isinstance(narration.get("tradeoff"), str)
            and isinstance(narration.get("risks"), list) and all(isinstance(x, str) for x in narration["risks"])):
        raise ProviderError("LLM 敘事欄位格式無效。")
    hits = list({hit.id: hit for group in evidence.values() for hit in group}.values())
    citations = coeffs.sources()
    adopted = [hit for hit in hits if f"{hit.source}:{hit.doc_id}" in citations]
    result.pop("intermediate")
    return {**result, "reasoning": narration["reasoning"], "tradeoff": narration["tradeoff"],
            "risks": narration["risks"], "citations": citations,
            "evidence": [asdict(hit) for hit in (adopted or hits[:5])]}
