import pytest
from types import SimpleNamespace

from agent_runner.core_port import CorePort
from checks.live_three_agents import SingleDecisionPort, main


@pytest.mark.asyncio
async def test_live_smoke_never_repeats_paid_planning(monkeypatch):
    calls = []
    async def decide(self, state, errors, emit):
        calls.append(state)
        return "fixture-decision"
    monkeypatch.setattr(CorePort, "decide", decide)
    port = SingleDecisionPort(None)
    assert await port.decide("snapshot", [], None) == "fixture-decision"
    with pytest.raises(RuntimeError, match="Single paid planning attempt"):
        await port.decide("retry", [], None)
    assert calls == ["snapshot"]
    assert port.failure == {"type": "PaidRetryNotAuthorized"}


def test_live_smoke_requires_paid_opt_in(monkeypatch):
    monkeypatch.setattr("sys.argv", ["live_three_agents"])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2


@pytest.mark.asyncio
async def test_five_tick_guard_caps_calls_and_rejects_same_tick(monkeypatch):
    async def decide(self, state, errors, emit):
        return state.tick
    monkeypatch.setattr(CorePort, "decide", decide)
    port = SingleDecisionPort(None, max_calls=5)
    for tick in range(5):
        assert await port.decide(SimpleNamespace(tick=tick), [], None) == tick
    with pytest.raises(RuntimeError):
        await port.decide(SimpleNamespace(tick=5), [], None)
    assert port.calls == 5
    port = SingleDecisionPort(None, max_calls=5)
    await port.decide(SimpleNamespace(tick=0), [], None)
    with pytest.raises(RuntimeError):
        await port.decide(SimpleNamespace(tick=0), [], None)
    assert port.calls == 1
