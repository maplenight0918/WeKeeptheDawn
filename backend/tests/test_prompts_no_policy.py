from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents.policy import assert_prompts_no_policy, find_policy_terms


# This intentionally lives in the test suite as an extensible acceptance list.
FORBIDDEN = ("always", "優先", "first", "平均", "most critical", "sorted by", "總是")


@pytest.mark.parametrize("term", FORBIDDEN)
def test_prompt_policy_terms_are_detected(term: str) -> None:
    assert term in find_policy_terms(f"Objective: {term} allocate resources", FORBIDDEN)


def test_prompt_objectives_and_constraints_are_allowed() -> None:
    assert find_policy_terms("Objective: maintain crew survival. Constraint: respect inventory and occupancy.") == []


def test_plant_agent_fixed_potato_allocation_is_rejected(tmp_path: Path) -> None:
    prompt = tmp_path / "plant.md"
    prompt.write_text("總是先灌溉馬鈴薯", encoding="utf-8")
    with pytest.raises(ValueError, match="plant.md"):
        assert_prompts_no_policy([prompt])


def test_all_prompt_templates_contain_no_policy_terms() -> None:
    directory = Path(__file__).resolve().parents[1] / "agents" / "prompts"
    for path in directory.glob("*.md"):
        assert find_policy_terms(path.read_text(encoding="utf-8"), FORBIDDEN) == [], path
