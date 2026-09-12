import copy
import json
import re
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.agent import HumanAgent
from app.retriever import Retriever
from app.discussion import expected_core_rules, rule_mismatches, map_discussion
from app.discussion_types import DiscussionRequest, DiscussionReply
from app.world_rules import ROOT

@pytest.fixture
def message():
    return json.loads((ROOT/'examples/discussion_requests/round1.json').read_text(encoding='utf-8'))

def second_round(message,reply):
    message=copy.deepcopy(message)
    message.update(round=2,message_id='core-request-human-002')
    message['content']['previous_messages']=[reply]
    message['content']['question']='請比較前輪建議，說明如何協調喝水與發電占用。'
    message['explanation']['follow_up_reason']='Plant 希望保留供水，Core 要求釐清補給占用。'
    return message

def test_actual_handoff_rule_profile_matches():
    blocks=re.findall(r'```json\s*\n(.*?)\n```',(ROOT/'specialist-agent-api-handoff.md').read_text(encoding='utf-8'),re.S)
    assert rule_mismatches(json.loads(blocks[0])['content']['rules'])==[]

def test_discussion_fixtures_preserve_chinese():
    for path in (ROOT/'examples/discussion_requests').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        assert re.search(r'[\u4e00-\u9fff]',data['content']['question'])
        assert '???' not in data['content']['question']

def test_unextended_core_sample_accepts_unknown_life():
    payload=json.loads((ROOT/'examples/discussion_requests/core_original_human.json').read_text(encoding='utf-8'))
    with TestClient(create_app(Settings())) as client:
        response=client.post('/discuss',json=payload)
    assert response.status_code==200
    DiscussionReply.model_validate(response.json())
    assert any('存活未知' in v for v in response.json()['content']['observations'])
    assert not response.json()['explanation']['follow_up_reason']
    snapshot,_=map_discussion(DiscussionRequest.model_validate(payload))
    assert snapshot.world_status=='planning' and snapshot.snapshot_phase=='between_ticks'
    assert all(c.alive is None for c in snapshot.crew)

def test_rounds_match_core_envelope_and_share_proposals(message):
    with TestClient(create_app(Settings())) as client:
        a=client.post('/discuss',json=message)
        assert a.status_code==200,a.text
        reply=a.json(); DiscussionReply.model_validate(reply)
        assert set(reply)=={'message_id','discussion_id','round','sender','recipient','world_version','display_text','explanation','content'}
        assert reply['sender']=='human' and reply['recipient']=='core'
        assert reply['message_id']!=message['message_id']
        assert reply['content']['observations']==reply['explanation']['observations']
        assert [p['proposal_id'] for p in reply['content']['suggested_actions']]==[p['proposal_id'] for p in reply['explanation']['proposals']]
        b=client.post('/discuss',json=second_round(message,reply))
        assert b.status_code==200,b.text
        assert b.json()['round']==2 and b.json()['world_version']==reply['world_version']
        assert b.json()['message_id']!=reply['message_id']

def test_extra_backend_fields_and_arbitrary_ids_preserved(message):
    world=message['content']['world']; world['paused_reason']='discussion'
    world['crew'][0]['name']='Pilot'; world['plots'][0]['backend_extra']=42
    snapshot,context=map_discussion(DiscussionRequest.model_validate(message))
    assert snapshot.crew[0].id=='crew-0' and snapshot.plots[0].id=='plot-0'
    assert snapshot.next_tick_plan is None and snapshot.water_production_available is None
    assert snapshot.world_status=='running'

def test_missing_world_status_defaults_to_planning(message):
    del message['content']['world']['world_status']
    snapshot,_=map_discussion(DiscussionRequest.model_validate(message))
    assert snapshot.world_status=='planning'
    message['content']['world']['world_status']='failed'
    snapshot,_=map_discussion(DiscussionRequest.model_validate(message))
    assert snapshot.world_status=='failed'

def test_continuous_planning_policy_does_not_change_accounting_rules(message):
    message['content']['rules']['planning']='World continues running during analysis; validate current state before apply.'
    snapshot,_=map_discussion(DiscussionRequest.model_validate(message))
    assert snapshot.world_status=='running'
    message['content']['rules']['generation']['power']=125
    assert rule_mismatches(message['content']['rules'])==['content.rules.generation.power']

@pytest.mark.parametrize('mutation',['coefficient','new_rule','version','world_version','schema','scope','extra_resource','duplicate_crew','invalid_phase','null_stock','alive_type'])
def test_incompatible_contract_rejected(message,mutation):
    content=message['content']; world=content['world']
    if mutation=='coefficient': content['rules']['generation']['power']=125
    if mutation=='new_rule': content['rules']['generation']['new_cost']=7
    if mutation=='version': world['rules_version']='unknown'
    if mutation=='world_version': world['world_version']=1
    if mutation=='schema': content['explanation_schema']['additionalProperties']=True
    if mutation=='scope': content['analysis_scope']=['food']
    if mutation=='extra_resource': world['resources']['co2']=500
    if mutation=='duplicate_crew': world['crew'][1]['id']=world['crew'][0]['id']
    if mutation=='invalid_phase': world['snapshot_phase']='after_base'
    if mutation=='null_stock': world['resources']['food']=None
    if mutation=='alive_type': world['crew'][0]['alive']='true'
    with TestClient(create_app(Settings())) as client:
        assert client.post('/discuss',json=message).status_code in {409,422}

@pytest.mark.parametrize('bad',['other_version','other_discussion','future_round','missing_history'])
def test_invalid_history_rejected(message,bad):
    with TestClient(create_app(Settings())) as client:
        reply=client.post('/discuss',json=message).json()
        follow=second_round(message,reply)
        if bad=='other_version': reply['world_version']+=1
        if bad=='other_discussion': reply['discussion_id']='other'
        if bad=='future_round': reply['round']=2
        if bad=='missing_history': follow['content']['previous_messages']=[]
        assert client.post('/discuss',json=follow).status_code in {409,422}

class DiscussionLLM:
    def __init__(self,invalid=False): self.calls=[]; self.invalid=invalid
    async def complete(self,messages,tools,deadline):
        self.calls.append(messages)
        context=json.loads(messages[1]['content'])['core_discussion']
        reviews=[]
        if context['round']==2:
            old=context['previous_messages'][0]
            reviews=[{'message_id':'invented' if self.invalid else old['message_id'],
                'proposal_id':old['explanation']['proposals'][0]['proposal_id'],
                'disposition':'needs_clarification','assessment':'請提供明確飲水與工作安排再核算。'}]
        return {'content':json.dumps({'recommendations':[], 'discussion':{'answer':'飲水與發電會競爭同一人的工作占用，請 Core 協調。',
            'reviews':reviews,'conflicts':['飲水與發電占用衝突。'],'uncertainties':[],
            'rule_ids':['crew.task.exclusive'],'evidence_ids':[]}})}

@pytest.mark.parametrize('invalid',[False,True])
def test_live_pipeline_receives_followup_and_checks_review_references(message,invalid):
    settings=Settings(agent_mode='live',retrieval_mode='bm25',llm_api_key='TEST',embedding_api_key='TEST')
    llm=DiscussionLLM(invalid); agent=HumanAgent(settings,Retriever(settings),llm)
    with TestClient(create_app(settings,agent)) as client:
        first=client.post('/discuss',json=message)
        assert first.status_code==200
        reply=first.json()
        reply['explanation']['proposals']=[{'proposal_id':'previous-real','strategy':'供水', 'reason':'需求','expected_effect':'待核算','tradeoffs':[],'evidence':[]}]
        follow=second_round(message,reply)
        response=client.post('/discuss',json=follow)
        assert response.status_code==(502 if invalid else 200)
        context=json.loads(llm.calls[-1][1]['content'])['core_discussion']
        assert context['question']==follow['content']['question']
        assert context['follow_up_reason']==follow['explanation']['follow_up_reason']
        assert context['previous_messages']==follow['content']['previous_messages']
        if not invalid: assert response.json()['explanation']['reviews'][0]['proposal_id']=='previous-real'

def test_provider_failure_is_non_2xx_with_baseline(message):
    class Failure:
        async def complete(self,*args): raise ValueError('do not leak provider text')
    s=Settings(agent_mode='live',retrieval_mode='bm25',llm_api_key='TEST',embedding_api_key='TEST')
    with TestClient(create_app(s,HumanAgent(s,Retriever(s),Failure()))) as client:
        response=client.post('/discuss',json=message)
    assert response.status_code==502 and 'baseline' in response.json()['detail']
    assert 'do not leak' not in response.text

def test_explicit_dead_crew_not_revived(message):
    message['content']['world']['crew'][0]['alive']=False
    with TestClient(create_app(Settings())) as client:
        response=client.post('/discuss',json=message)
    assert response.status_code==200
    assert not response.json()['content']['suggested_actions']
    assert '已失敗' in response.json()['display_text']
