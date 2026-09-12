"""Transport fixtures only: no live model requests or API keys required."""
import json

import httpx
import pytest

from backend.integration.openai_client import OpenAIClient, ModelResponseError, response_text
from backend.integration.settings import OpenAISettings


async def test_responses_request_uses_env_auth_and_caller_schema(monkeypatch):
    monkeypatch.setenv('TEST_MODEL_KEY', 'test-only-key')
    monkeypatch.setenv('TEST_MODEL_ID', 'test-model')
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': '{"ok":true}'}]}
        ]})
    settings = OpenAISettings(api_key_env='TEST_MODEL_KEY', model_env='TEST_MODEL_ID')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OpenAIClient(settings, client).complete_json(
            instructions='Return an object.', input='Test input', schema={'type': 'object'})
    assert result == {'ok': True}
    assert received[0].headers['authorization'] == 'Bearer test-only-key'
    body = json.loads(received[0].content)
    assert body['model'] == 'test-model'
    assert body['text']['format']['schema'] == {'type': 'object'}
    assert body['store'] is False
    assert 'test-only-key' not in received[0].content.decode()


async def test_missing_key_fails_without_network(monkeypatch):
    monkeypatch.delenv('MISSING_TEST_MODEL_KEY', raising=False)
    with pytest.raises(ModelResponseError, match='MISSING_TEST_MODEL_KEY'):
        await OpenAIClient(OpenAISettings(api_key_env='MISSING_TEST_MODEL_KEY')).complete(instructions='', input='')


async def test_http_error_never_echoes_response_body_or_key(monkeypatch):
    monkeypatch.setenv('TEST_MODEL_KEY', 'test-only-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(401, json={'error': 'test-only-secret'})
    )) as client:
        with pytest.raises(ModelResponseError) as caught:
            await OpenAIClient(OpenAISettings(api_key_env='TEST_MODEL_KEY', model='test-model'), client).complete(
                instructions='', input='')
    assert '401' in str(caught.value)
    assert 'test-only-secret' not in str(caught.value)


@pytest.mark.parametrize('response', [
    {'status': 'incomplete', 'output': []},
    {'output': [{'content': [{'type': 'refusal', 'refusal': 'no'}]}]},
    {'status': 'completed', 'output': []},
])
def test_incomplete_refused_or_empty_output_is_not_used(response):
    with pytest.raises(ModelResponseError):
        response_text(response)
