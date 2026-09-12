import asyncio
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.request_lifecycle import diagnostic_codes, while_connected


def test_safe_codes_do_not_leak_arbitrary_warnings():
    result = SimpleNamespace(warnings=['provider_timeout', 'secret key', 'provider_http_429'],
                             retrieval=SimpleNamespace(fallback_reason=None))
    assert diagnostic_codes(result) == ['provider_timeout', 'provider_http_429']


def test_disconnect_cancels_old_request_and_releases_slot():
    async def run():
        gone = asyncio.Event()
        started = asyncio.Event()
        released = asyncio.Event()
        slot = asyncio.Semaphore(1)
        class Request:
            async def receive(self):
                await gone.wait()
                return {'type': 'http.disconnect'}
        async def old_work():
            async with slot:
                started.set()
                try: await asyncio.Event().wait()
                finally: released.set()
        pending = asyncio.create_task(while_connected(Request(), old_work()))
        await started.wait()
        gone.set()
        with pytest.raises(HTTPException) as caught: await pending
        assert caught.value.status_code == 499
        assert released.is_set()
        async with asyncio.timeout(1):
            async with slot: pass
    asyncio.run(run())


def test_normal_response_and_outer_cancellation():
    async def run():
        class Request:
            async def receive(self): await asyncio.Event().wait()
        async def complete(): return 'new conversation'
        assert await while_connected(Request(), complete()) == 'new conversation'
        cleaned = asyncio.Event()
        started = asyncio.Event()
        async def work():
            started.set()
            try: await asyncio.Event().wait()
            finally: cleaned.set()
        task = asyncio.create_task(while_connected(Request(), work()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert cleaned.is_set()
    asyncio.run(run())
