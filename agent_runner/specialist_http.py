"""Cancellable specialist transport. Does not own agent decisions or retries."""
import httpx
from core_agent.core_agent import HTTPSpecialist
from core_agent.core_agent.contracts import Message

SAFE_CODES = frozenset({'provider_timeout', 'provider_connection_error', 'provider_invalid_json',
    'analysis_deadline_exceeded', 'llm_invalid_output', 'llm_response_incomplete',
    'llm_response_invalid', 'llm_call_budget_exceeded', 'tool_call_budget_exceeded',
    'missing_api_key', 'missing_llm_model', 'invalid_tool_input', 'invalid_proposal',
    'retrieval_degraded', 'analysis_degraded'} | {f'provider_http_{i}' for i in range(100, 600)})


class SpecialistFailure(RuntimeError):
    def __init__(self, agent, status, codes):
        self.codes = [f'{agent}_http_{status}', *codes]
        super().__init__('Specialist request failed')


class CancellableSpecialist(HTTPSpecialist):
    async def ask(self, message):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.url, json=message.to_dict(),
                headers={'Authorization': f'Bearer {self.token}'} if self.token else {})
        if response.is_error:
            codes = []
            try:
                detail = response.json().get('detail', {})
                raw = detail.get('error_codes', []) if isinstance(detail, dict) else []
                if isinstance(raw, list):
                    codes = [c for c in raw if isinstance(c, str) and c in SAFE_CODES][:8]
            except (ValueError, AttributeError):
                pass
            agent = message.recipient if message.recipient in {'human', 'plant'} else 'specialist'
            raise SpecialistFailure(agent, response.status_code, codes)
        data = response.json()
        return Message(**{k: v for k, v in data.items() if k != 'detail_text'})
