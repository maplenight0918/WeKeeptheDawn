import asyncio
import hashlib
import json
import httpx
import numpy as np
import pytest
from app.agent import HumanAgent, Proposal, proposal_output
from app.providers import EmbeddingClient, REQUEST_METRICS, Deadline
from app.retriever import Retriever
from app.settings import Settings
from app.evidence_review import reviewed_claims
from app.world_rules import ROOT

def test_concurrent_embedding_diagnostics_are_request_scoped(snapshot):
    async def run():
        arrivals=0; together=asyncio.Event()
        async def handler(request):
            nonlocal arrivals
            arrivals+=1
            if arrivals==2: together.set()
            await together.wait()
            vector=[1.0]+[0.0]*1023
            return httpx.Response(200,json={'data':[{'index':0,'embedding':vector}]})
        class EmptyLLM:
            async def complete(self,*args):
                await asyncio.sleep(0.01)
                return {'content':'{"recommendations":[]}'}
        s=Settings(agent_mode='live',embedding_api_key='TEST',llm_api_key='TEST')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            embed=EmbeddingClient(s,client); agent=HumanAgent(s,Retriever(s,embed),EmptyLLM())
            a,b=await asyncio.gather(agent.analyze(snapshot),agent.analyze(snapshot))
            assert embed.calls==2
            assert a.diagnostics['embedding_calls']==b.diagnostics['embedding_calls']==1
            assert a.diagnostics['cache_hits']==b.diagnostics['cache_hits']==0
            c=await agent.analyze(snapshot)
            assert c.diagnostics['embedding_calls']==0 and c.diagnostics['cache_hits']==1
            assert REQUEST_METRICS.get() is None
    asyncio.run(run())

def test_request_metrics_reset_on_cancel(snapshot):
    class WaitingRetriever:
        metadata={}; index_metadata={}
        def info(self): return {'requested_mode':'dense','actual_mode':'not_used','fallback_reason':None,'model':None,'dimensions':None}
        async def retrieve(self,*args,**kwargs): await asyncio.sleep(10)
    async def run():
        agent=HumanAgent(Settings(agent_mode='live'),WaitingRetriever())
        task=asyncio.create_task(agent.analyze(snapshot)); await asyncio.sleep(0.01); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert REQUEST_METRICS.get() is None
    asyncio.run(run())

@pytest.mark.parametrize('number',['3.217','0.895','12.778'])
def test_numeric_anchors_rescue_missed_dense_results(number):
    s=Settings(); r=Retriever(s)
    # Force cosine top-5 to miss the BVAD table, independently of remote model drift.
    assert r.vectors is not None
    r.vectors[:]=0; r.vectors[:5,0]=1
    async def fake(query,deadline): return np.array([1]+[0]*1023,dtype=np.float32)
    r.embedding.embed_query=fake
    async def run():
        docs,info=await r.retrieve('nominal potable water oxygen energy '+number,5,Deadline(1))
        assert info['actual_mode']=='mixed' and info['fallback_reason'] is None
        assert any(number in d['excerpt'] for d in docs)
    asyncio.run(run())

def test_anchor_rejects_substring_number():
    from app.retriever import tokens
    assert '3.217' not in tokens('13.217')

def test_reviewed_claims_are_bound_to_exact_source():
    chunks=[json.loads(line) for line in (ROOT/'data/chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    c=next(c for c in chunks if c['chunk_id']=='bvad_2022-p72-0-72b803e99f')
    assert len(reviewed_claims(c['chunk_id'],c['text']))==2
    assert not reviewed_claims(c['chunk_id'],c['text'].replace('3.217','999'))
    assert not reviewed_claims('forged',c['text'])

def test_false_scientific_prose_not_published(snapshot):
    p=Proposal(proposal_id='test',proposal_kind='eat',target_crew_ids=['crew-1'],reason='NASA proved that eating cures all disease and produces 999999 oxygen.',rule_ids=['crew.refill.transfer'],evidence_ids=[])
    response=proposal_output(p,snapshot,set(),{})
    assert '999999' not in json.dumps(response) and 'cures' not in response['reason']
    assert 'not published' in ' '.join(response['constraints'])

def test_audit_reference_resolves_original_plan(snapshot):
    from app.plan_auditor import audit_next_tick
    candidate=snapshot.next_tick_plan
    audit=audit_next_tick(snapshot,candidate)
    audits={json.dumps(candidate.model_dump(),sort_keys=True):audit}
    p=Proposal(proposal_id='ref',proposal_kind='adjust_generation',target_crew_ids=['crew-1'],reason='Review work.',rule_ids=['generation.proportional'],evidence_ids=[],audit_result_id=audit['result_id'])
    result=proposal_output(p,snapshot,set(),audits)
    assert result['audit_result_id']==audit['result_id'] and result['expected_effect']['candidate_audit']==audit
    assert result['proposed_changes']['candidate_plan']==candidate.model_dump()
    p.audit_result_id='invented'
    with pytest.raises(ValueError): proposal_output(p,snapshot,set(),audits)
