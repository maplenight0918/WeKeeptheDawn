"""Metadata prefilter followed by normalized vector dot products."""
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import INDEX
from src.retrieval.embedder import embed


@dataclass
class Hit:
    id: str
    score: float
    text: str
    doc_id: str
    source: str
    title: str
    year: str
    tier: str
    section: str
    crops: list[str]
    units: list[str]

    def citation(self) -> str:
        y = f" ({self.year})" if self.year else ""
        return f"[{self.source}:{self.doc_id}] {self.title}{y}"


def as_context(hits, max_chars=12000):
    blocks = []
    for i, hit in enumerate(hits, 1):
        blocks.append(f"[{i}] {hit.citation()}\n"
                      f"    section: {hit.section} | units: {', '.join(hit.units)}\n{hit.text}")
    return "\n\n".join(blocks)[:max_chars]


class CorpusStore:
    def __init__(self, index_dir=INDEX):
        index_dir = Path(index_dir)
        self.vecs = np.load(index_dir / "embeddings.npy")
        self.ids = json.loads((index_dir / "ids.json").read_text(encoding="utf-8"))
        with (index_dir / "chunks.jsonl").open(encoding="utf-8") as stream:
            self.chunks = {c["id"]: c for c in map(json.loads, stream)}
        if self.vecs.shape != (len(self.ids), 1024) or len(set(self.ids)) != len(self.ids):
            raise ValueError("Corpus vector/ID alignment is invalid")
        self.rows = [self.chunks[id_] for id_ in self.ids]

    def search(
        self,
        query: str,
        k: int = 8,
        tiers: list[str] | None = ("A_plant_core", "B_usable"),
        crops: list[str] | None = None,
        units: list[str] | None = None,
        require_all_units: bool = False,
        max_per_doc: int = 2,
        fallback: bool = True,
    ) -> list[Hit]:
        if k <= 0:
            return []

        def filtered(crop_filter, unit_filter):
            return np.array([
                i for i, chunk in enumerate(self.rows)
                if (not tiers or chunk["tier"] in tiers)
                and (not crop_filter or set(crop_filter).intersection(chunk["crops"]))
                and (not unit_filter or (
                    set(unit_filter).issubset(chunk["units"]) if require_all_units
                    else bool(set(unit_filter).intersection(chunk["units"]))
                ))
            ], dtype=np.intp)

        idx = filtered(crops, units)
        if fallback and len(idx) < k and units:
            units = None
            idx = filtered(crops, units)
        if fallback and len(idx) < k and crops:
            idx = filtered(None, units)
        if not len(idx):
            return []
        qv = embed(query)
        scores = self.vecs[idx] @ qv
        take = min(len(idx), k * max(max_per_doc, 1) * 4)
        top = idx[np.argpartition(-scores, take - 1)[:take]]
        top = top[np.argsort(-(self.vecs[top] @ qv))]
        counts = Counter()
        hits = []
        for i in top:
            chunk = self.rows[i]
            doc = (chunk["source"], chunk["doc_id"])
            if max_per_doc > 0 and counts[doc] >= max_per_doc:
                continue
            counts[doc] += 1
            fields = {name: chunk.get(name, "") for name in Hit.__dataclass_fields__ if name != "score"}
            hits.append(Hit(score=float(self.vecs[i] @ qv), **fields))
            if len(hits) == k:
                break
        return hits

    # coefficient_evidence is appended verbatim from SPEC §5.

    def coefficient_evidence(self, coeff, crop=None, k=4):
        spec = {
            "biomass_rate": (
                ["biomass_rate", "yield_value", "harvest_weight"],
                "edible biomass productivity per unit area per day, "
                "dry weight yield in controlled environment"),
            "lue": (
                ["ppfd", "biomass_rate", "yield_value"],
                "light use efficiency, grams of biomass per mole of photons, "
                "daily light integral and growth"),
            "transpiration": (
                ["water_use"],
                "crop transpiration rate, water consumption per day, "
                "water use efficiency in growth chamber"),
            "o2_rate": (
                ["gas_exchange", "biomass_rate"],
                "oxygen production rate by plants, photosynthetic gas exchange, "
                "stoichiometry of biomass and oxygen"),
            "energy": (
                ["energy_use", "ppfd"],
                "LED lighting power consumption per square meter, "
                "energy requirement of plant growth chamber"),
            "photoperiod": (
                ["photoperiod", "ppfd"],
                "photoperiod and light intensity effect on crop yield"),
            "growth_days": (
                ["growth_rate", "harvest_weight"],
                "days to harvest, crop growth cycle duration"),
            "wue": (
                ["water_use", "yield_value", "harvest_weight"],
                "water use efficiency, grams of biomass per liter of water, "
                "irrigation water productivity in controlled environment"),
            "led_power": (
                ["energy_use", "ppfd"],
                "LED lighting power consumption per square meter, "
                "energy requirement of plant growth chamber"),
        }
        
        units, q = spec.get(coeff, ([], coeff))
        if crop:
            q = f"{crop}: {q}"          # 作物名加在查詢語句前面
        return self.search(q, k=k, crops=[crop] if crop else None, units=units)
