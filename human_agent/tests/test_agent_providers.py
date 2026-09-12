import asyncio
import copy
import json
import time
import httpx
import numpy as np
import pytest
from app.agent import HumanAgent, Proposal, FinalProposals, proposal_output, validate_candidate, TOOLS
from app.schemas import AnalyzeRequest, Plan
from app.providers import Deadline, EmbeddingClient, LLMClient, ProviderError, post_json
from app.retriever import Retriever, world_route
from app.settings import Settings, ConfigurationError

def test_t25_forged_citations_and_state_fields(snapshot):
    p=Proposal(proposal_id='fake',proposal_kind='eat',target_crew_ids=['crew-1'],reason='fake',rule_ids=['crew.refill.transfer'],evidence_ids=['invented'])
    with pytest.raises(ValueError): proposal_output(p,snapshot,set(),{})
    with pytest.raises(ValueError): FinalProposals.model_validate({'recommendations':[],'resources':{'food':999999}})
    with pytest.raises(ValueError): FinalProposals.model_validate({'recommendations':[],'rules':{'daily_energy':1}})

def test_t25_crop_occupation_protected(raw):
    raw['next_tick_plan']['crew_tasks'][0]={'crew_id':'crew-1','task':'harvest','plot_id':'plot-1'}
    raw['next_tick_plan']['crop_operation_order']=['crew-1']
    s=AnalyzeRequest.model_validate(raw); p=s.next_tick_plan.model_dump()
    p['crew_tasks'][0]={'crew_id':'crew-1','task':'generate','work_fraction':1}; p['crop_operation_order']=[]
    with pytest.raises(ValueError): validate_candidate(s,Plan.model_validate(p))

@pytest.mark.parametrize('status,retries',[(401,1),(429,3),(503,3)])
def test_t26_provider_retry_status(status,retries):
    calls=[]
    def handle(request):
        calls.append(request); return httpx.Response(status,json={'secret':'must not be reported'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(ProviderError,match='provider_http_'+str(status)):
                await post_json('https://example.test/embeddings','PRIVATE_TEST_TOKEN',{},1,Deadline(5),client)
    asyncio.run(run()); assert len(calls)==retries

def test_t26_invalid_provider_json():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,text='not json'))) as client:
            with pytest.raises(ProviderError,match='invalid_json'): await post_json('https://example.test','test',{},1,Deadline(1),client)
    asyncio.run(run())

def test_t26_real_async_cancellation_no_background_workers():
    active=0; cancelled=0
    async def handle(request):
        nonlocal active,cancelled
        active+=1
        try: await asyncio.sleep(5)
        except asyncio.CancelledError: cancelled+=1; raise
        finally: active-=1
        return httpx.Response(200,json={})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            for _ in range(3):
                with pytest.raises(ProviderError,match='timeout'):
                    await post_json('https://example.test','test',{},0.02,Deadline(1),client)
            assert active==0 and cancelled==3
    asyncio.run(run())

def test_t26_stale_index_fallback_and_no_bm25(tmp_path):
    s=Settings(index_dir=str(tmp_path)); r=Retriever(s)
    async def run():
        docs,info=await r.retrieve('oxygen consumption',5,Deadline(1))
        assert docs==[] and info['actual_mode']=='none' and 'bm25_missing' in info['fallback_reason']
        assert world_route('個人能量歸零規則')==['crew.personal.death']
        docs,info=await r.retrieve('遊戲製水是否是物理守恆',5,Deadline(1))
        assert docs[0]['rule_id']=='water_production.conversion'
    asyncio.run(run())

def test_t26_llm_failure_preserves_critical(raw):
    raw['crew'][0]['food_energy']=1
    class BadLLM:
        async def complete(self,*args): raise ProviderError('provider_http_401')
    s=Settings(agent_mode='live',retrieval_mode='bm25',llm_api_key='TEST',embedding_api_key='TEST')
    response=asyncio.run(HumanAgent(s,Retriever(s),BadLLM()).analyze(AnalyzeRequest.model_validate(raw)))
    assert response.execution_mode=='degraded' and response.next_tick_audit.fatal_stage=='base'
    assert any(r.severity=='critical' for r in response.risks)
    assert 'TEST' not in response.model_dump_json()

def test_mock_and_deterministic_never_network(raw):
    class Never:
        async def complete(self,*args): raise AssertionError('network forbidden')
    s=Settings(); r=Retriever(s)
    async def forbidden(*args): raise AssertionError('embedding network forbidden')
    r.embedding.embed_query=forbidden
    agent=HumanAgent(s,r,Never())
    response=asyncio.run(agent.analyze(AnalyzeRequest.model_validate(raw)))
    assert response.execution_mode=='mock'
    raw['analysis']['include_recommendations']=False
    response=asyncio.run(agent.analyze(AnalyzeRequest.model_validate(raw)))
    assert response.execution_mode=='deterministic' and response.retrieval.actual_mode=='not_used' and not response.tool_trace

def test_candidate_tool_loop_and_verified_scope(snapshot):
    candidate=snapshot.next_tick_plan.model_dump(); candidate['crew_tasks'][0]['work_fraction']=0.5
    class Scripted:
        calls=0
        async def complete(self,*args):
            self.calls+=1
            if self.calls==1:
                return {'role':'assistant','content':None,'tool_calls':[{'id':'a1','type':'function','function':{'name':'audit_human_plan','arguments':json.dumps({'plan':candidate})}}]}
            return {'content':json.dumps({'recommendations':[{'proposal_id':'less_work','proposal_kind':'adjust_generation','target_crew_ids':['crew-1'],'reason':'Reduce personal workload subject to Core review.','rule_ids':['generation.proportional'],'evidence_ids':[],'candidate_plan':candidate}]})}
    s=Settings(agent_mode='live',retrieval_mode='bm25',llm_api_key='TEST',embedding_api_key='TEST')
    r=asyncio.run(HumanAgent(s,Retriever(s),Scripted()).analyze(snapshot))
    assert r.execution_mode=='live' and r.recommendations[0].feasibility=='verified_for_audited_scope'
    assert r.recommendations[0].audit_result_id and r.recommendations[0].expected_effect
    assert any(t['tool']=='retrieve_evidence' for t in r.tool_trace)
    assert r.next_tick_audit.known_after_values['crew']['crew-1']['food_energy']==2172.75

def test_reject_llm_forged_output_preserves_baseline(snapshot):
    class Forged:
        async def complete(self,*args):
            return {'content':json.dumps({'recommendations':[{'proposal_id':'x','proposal_kind':'eat','target_crew_ids':['crew-1'],'reason':'false','rule_ids':['fake_rule'],'evidence_ids':['fake_source']}]})}
    s=Settings(agent_mode='live',retrieval_mode='bm25',llm_api_key='TEST',embedding_api_key='TEST')
    r=asyncio.run(HumanAgent(s,Retriever(s),Forged()).analyze(snapshot))
    assert r.execution_mode=='degraded' and r.recommendations==[]

def test_embedding_reorders_and_validates_dimensions():
    s=Settings(embedding_dimensions=3,embedding_api_key='TEST')
    async def run():
        def handler(request): return httpx.Response(200,json={'data':[{'index':1,'embedding':[0,2,0]},{'index':0,'embedding':[3,0,0]}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            vectors=await EmbeddingClient(s,client).embed_documents(['a','b'],Deadline(1))
            assert np.array_equal(vectors,np.array([[1,0,0],[0,1,0]],dtype=np.float32))
    asyncio.run(run())

@pytest.mark.parametrize('vectors',[[[0,0,0]],[[1,0]],[[float('nan'),0,0]],[[float('inf'),0,0]]])
def test_embedding_rejects_invalid_vectors(vectors):
    with pytest.raises(ProviderError): EmbeddingClient(Settings(embedding_dimensions=3)).validate_vectors(vectors,1)

def test_t27_identity_and_query_cache_bound():
    a=EmbeddingClient(Settings()); b=EmbeddingClient(Settings(embedding_dimensions=768)); c=EmbeddingClient(Settings(embedding_input_type_policy='query_document'))
    assert len({client.cache_key('same') for client in [a,b,c]})==3
    async def fake(texts,kind,deadline): return np.ones((1,1024),dtype=np.float32)
    a._embed=fake
    async def run():
        for i in range(260): await a.embed_query(str(i),Deadline(1))
        assert len(a.query_cache)==256
        await a.embed_query('259',Deadline(1)); assert a.cache_hits==1
    asyncio.run(run())

def test_old_profile_fails_and_no_key_substitution():
    with pytest.raises(ConfigurationError,match='PARAMETER_PROFILE'): Settings(parameter_profile='scientific').validate()
    s=Settings(embedding_api_key='embedding-only')
    assert 'LLM_API_KEY' in s.missing() and s.llm_api_key==''
    assert 'embedding-only' not in repr(s)

def test_tools_schema_references_resolve():
    assert '$ref' not in json.dumps(TOOLS)
