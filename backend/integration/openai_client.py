"""Generic Responses transport for teammate code; no agent or planning policy.

Official contract: https://developers.openai.com/api/docs/quickstart
The caller supplies all instructions, input and any output schema.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
import jsonschema

from backend.integration.settings import OpenAISettings


class ModelResponseError(RuntimeError):
    pass


def response_text(response: dict[str, Any]) -> str:
    if response.get('status') not in (None, 'completed'):
        raise ModelResponseError('Model response was not completed')
    parts = []
    for item in response.get('output', []):
        for content in item.get('content', []):
            if content.get('type') == 'refusal':
                raise ModelResponseError('Model declined this request')
            if content.get('type') == 'output_text':
                parts.append(content.get('text', ''))
    if not parts:
        raise ModelResponseError('Model response did not contain output text')
    return ''.join(parts)


class OpenAIClient:
    def __init__(self, settings: OpenAISettings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def complete(self, *, instructions: str, input: str | list[dict[str, Any]],
                       schema: dict[str, Any] | None = None) -> str:
        key = os.environ.get(self.settings.api_key_env)
        model = self.settings.model or os.environ.get(self.settings.model_env)
        if not key:
            raise ModelResponseError(f'Set server environment variable {self.settings.api_key_env}')
        if not model:
            raise ModelResponseError(f'Choose a model in YAML or {self.settings.model_env}')
        payload: dict[str, Any] = {'model': model, 'instructions': instructions, 'input': input, 'store': False}
        if schema is not None:
            # The wire schema includes open dictionaries. Do not claim strict
            # Structured Outputs compatibility; validate the returned model locally.
            payload['text'] = {'format': {'type': 'json_schema', 'name': 'agent_payload',
                                          'schema': schema, 'strict': False}}
        headers = {'Authorization': f'Bearer {key}'}

        async def send(client):
            try:
                response = await client.post(self.settings.base_url.rstrip('/') + '/responses',
                                             headers=headers, json=payload,
                                             timeout=self.settings.timeout_seconds)
                if response.is_error:
                    raise ModelResponseError(f'OpenAI request failed (HTTP {response.status_code})')
                return response_text(response.json())
            except httpx.HTTPError:
                raise ModelResponseError('OpenAI network request failed') from None
            except (ValueError, KeyError, TypeError):
                raise ModelResponseError('OpenAI returned an invalid response') from None

        if self.client is not None:
            return await send(self.client)
        async with httpx.AsyncClient() as client:
            return await send(client)

    async def complete_json(self, *, instructions: str, input: str | list[dict[str, Any]],
                            schema: dict[str, Any]) -> dict[str, Any]:
        text = await self.complete(instructions=instructions, input=input, schema=schema)
        try:
            result = json.loads(text)
        except ValueError:
            raise ModelResponseError('Model output is not valid JSON') from None
        if not isinstance(result, dict):
            raise ModelResponseError('Model output must be a JSON object')
        try:
            jsonschema.validate(result, schema)
        except jsonschema.ValidationError:
            raise ModelResponseError('Model output does not match the supplied schema') from None
        return result
