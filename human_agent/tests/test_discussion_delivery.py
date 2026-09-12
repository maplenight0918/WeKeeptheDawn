import copy
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.world_rules import ROOT
from app.discussion_types import DiscussionReply
from examples.discussion_client import validate_reply, follow_up

@pytest.fixture
def message():
    return json.loads((ROOT/'examples/discussion_requests/current_plan.json').read_text(encoding='utf-8'))

def test_swagger_examples_are_valid_requests():
    with TestClient(create_app(Settings())) as client:
        examples=client.get('/openapi.json').json()['paths']['/discuss']['post']['requestBody']['content']['application/json']['examples']
        assert 'core_original_human' in examples and 'current_plan' in examples
        for example in examples.values():
            response=client.post('/discuss',json=example['value'])
            assert response.status_code==200,response.text
            DiscussionReply.model_validate(response.json())

def test_manual_client_three_rounds_preserves_snapshot_and_real_history(message):
    original=copy.deepcopy(message['content']['world'])
    with TestClient(create_app(Settings())) as client:
        for number in [1,2,3]:
            reply=client.post('/discuss',json=message).json()
            validate_reply(reply,message)
            assert len(message['content']['previous_messages'])==number-1
            assert message['content']['world']==original
            if number<3: message=follow_up(message,reply,'請評論前輪建議。')
        with pytest.raises(ValueError): follow_up(message,reply,'第四輪不合法')

@pytest.mark.parametrize('fault',['version','round_type','reused_id','proposal_link','invented_review'])
def test_manual_client_rejects_wrong_reply(message,fault):
    with TestClient(create_app(Settings())) as client: reply=client.post('/discuss',json=message).json()
    if fault=='version': reply['world_version']+=1
    if fault=='round_type': reply['round']=True
    if fault=='reused_id': reply['message_id']=message['message_id']
    if fault=='proposal_link': reply['content']['suggested_actions']=[{'proposal_id':'invented'}]
    if fault=='invented_review': reply['explanation']['reviews']=[{'message_id':'invented','proposal_id':'invented'}]
    with pytest.raises(ValueError): validate_reply(reply,message)

def test_failure_and_current_plan_fixtures(message):
    with TestClient(create_app(Settings())) as client:
        reply=client.post('/discuss',json=message).json()
        assert any('原計畫預檢狀態：feasible_in_scope' in s for s in reply['content']['observations'])
        dead=json.loads((ROOT/'examples/discussion_requests/already_failed.json').read_text(encoding='utf-8'))
        reply=client.post('/discuss',json=dead).json()
        assert not reply['content']['suggested_actions'] and '已失敗' in reply['display_text']
