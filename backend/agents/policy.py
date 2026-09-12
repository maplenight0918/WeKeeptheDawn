"""Audit system prompt templates; model replies are not policy templates."""
from __future__ import annotations

import re
from pathlib import Path


POLICY_TERMS = ("always", "優先", "first", "平均", "most critical", "sorted by", "總是")


def find_policy_terms(text: str, terms: tuple[str, ...] = POLICY_TERMS) -> list[str]:
    def matches(term: str) -> bool:
        pattern = re.escape(term)
        if term.isascii():
            pattern = r"\b" + pattern.replace(r"\ ", r"\s+") + r"\b"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None

    return [term for term in terms if matches(term)]


def assert_prompts_no_policy(paths: list[Path]) -> None:
    violations = {
        str(path): found for path in paths
        if (found := find_policy_terms(path.read_text(encoding="utf-8")))
    }
    if violations:
        raise ValueError(f"Prompt allocation policy terms found: {violations}")
