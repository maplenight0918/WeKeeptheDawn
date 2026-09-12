import asyncio
import httpx
import pytest
from core_agent.core_agent.contracts import Message
from agent_runner.specialist_http import CancellableSpecialist, SpecialistFailure
from agent_runner.runner import failure_codes


@pytest.mark.asyncio
async def test_specialist_error_codes_are_filtered(monkeypatch):
    real_client = httpx.AsyncClient
    async def handler(request):
        return httpx.Response(502, json={'detail': {'error_codes': ['provider_timeout', 'secret-key', {}]}})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    specialist = CancellableSpecialist('http://127.0.0.1:8102/discuss')
    with pytest.raises(SpecialistFailure) as caught:
        await specialist.ask(Message('new-discussion', 1, 'core', 'human', 8, {}))
    assert failure_codes(caught.value) == ['human_http_502', 'provider_timeout']


@pytest.mark.asyncio
async def test_cancel_closes_inflight_specialist_request(monkeypatch):
    real_client = httpx.AsyncClient
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def handler(request):
        started.set()
        try: await asyncio.Event().wait()
        finally: cancelled.set()
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    task = asyncio.create_task(CancellableSpecialist('http://127.0.0.1:8102/discuss').ask(
        Message('old-discussion', 1, 'core', 'human', 7, {})))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert cancelled.is_set()
