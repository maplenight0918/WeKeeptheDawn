from urllib.error import HTTPError

from agent_runner.runner import failure_codes


def test_failure_codes_preserve_http_status_without_secrets():
    inner = HTTPError('https://secret.example', 502, 'secret body', {}, None)
    outer = RuntimeError('secret token')
    outer.__cause__ = inner
    assert failure_codes(outer) == ['planning_error', 'http_502']


def test_failure_codes_timeout_and_cycle_are_bounded():
    error = TimeoutError('secret')
    error.__cause__ = error
    assert failure_codes(error) == ['timeout']
