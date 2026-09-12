"""HTTP lifecycle and allowlisted diagnostics; no model or strategy changes."""
import asyncio
import re
from fastapi import HTTPException


def diagnostic_codes(result):
    allowed = {'provider_timeout', 'provider_connection_error', 'provider_invalid_json',
               'analysis_deadline_exceeded', 'llm_invalid_output', 'llm_response_incomplete',
               'llm_response_invalid', 'llm_call_budget_exceeded', 'tool_call_budget_exceeded',
               'missing_api_key', 'missing_llm_model'}
    mapped = {
        'Rejected invalid or unauthorized LLM tool input.': 'invalid_tool_input',
        'Rejected proposal: unsupported citation, unauthorized plan change, or missing candidate audit.': 'invalid_proposal',
    }
    codes = []
    for warning in result.warnings:
        code = mapped.get(warning)
        if warning in allowed or re.fullmatch(r'provider_http_[1-5][0-9]{2}', warning): code = warning
        if code and code not in codes: codes.append(code)
    if result.retrieval.fallback_reason not in (None, 'world_rule_routing'):
        codes.append('retrieval_degraded')
    return codes or ['analysis_degraded']


async def while_connected(request, work):
    async def disconnected():
        # Body has already been parsed by FastAPI. Wait for the ASGI disconnect
        # directly; is_disconnected() uses a cancel scope that can swallow cleanup.
        while True:
            if (await request.receive())['type'] == 'http.disconnect': return
    task = asyncio.create_task(work)
    watcher = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            watcher.result()
            raise HTTPException(499, detail={'error': 'client_disconnected'})
        return await task
    finally:
        task.cancel()
        watcher.cancel()
        await asyncio.gather(task, watcher, return_exceptions=True)
