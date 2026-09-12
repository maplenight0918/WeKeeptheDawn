import asyncio
import hashlib
import json
import numpy as np
from app.providers import EmbeddingClient
from app.settings import Settings
from app.world_rules import digest
from scripts import build_index

def test_t27_incremental_reuse_change_delete_policy_atomic(tmp_path,monkeypatch):
    (tmp_path/'data').mkdir()
    monkeypatch.setattr(build_index,'ROOT',tmp_path)
    calls=[]
    async def fake(self,texts,deadline):
        calls.extend(texts)
        return np.array([[1,0,0] for _ in texts],dtype=np.float32)
    monkeypatch.setattr(EmbeddingClient,'embed_documents',fake)
    settings=Settings(index_dir=str(tmp_path/'index'),embedding_dimensions=3,embedding_api_key='TEST')
    def corpus(texts):
        chunks=[{'chunk_id':'c'+str(i),'text':text,'hash':hashlib.sha256(text.encode()).hexdigest()} for i,text in enumerate(texts)]
        (tmp_path/'data/chunks.jsonl').write_text('\n'.join(json.dumps(c) for c in chunks),encoding='utf-8')
        (tmp_path/'data/corpus_metadata.json').write_text(json.dumps({'corpus_version':'corpus-'+digest([(c['chunk_id'],c['hash']) for c in chunks])[:16]}))
    corpus(['first original','second original'])
    assert asyncio.run(build_index.build(settings,'both'))==0 and len(calls)==2
    calls.clear()
    assert asyncio.run(build_index.build(settings,'dense',True))==0 and calls==[]
    corpus(['first original','second changed'])
    assert asyncio.run(build_index.build(settings,'dense'))==0 and calls==['second changed']
    calls.clear(); corpus(['first original'])
    assert asyncio.run(build_index.build(settings,'dense',True))==0 and calls==[]
    pointer=json.loads((tmp_path/'index/current.json').read_text())
    generation=tmp_path/'index/generations'/pointer['generation']
    assert json.loads((generation/'chunk_ids.json').read_text())==['c0']
    settings.embedding_dimensions=4
    assert asyncio.run(build_index.build(settings,'dense',True))==2
    assert json.loads((tmp_path/'index/current.json').read_text())==pointer

def test_responses_adapter_tool_roundtrip():
    import httpx
    from app.providers import LLMClient, Deadline
    async def run():
        seen=[]
        def handle(request):
            body=json.loads(request.content); seen.append(body)
            assert request.url.path=='/v1/responses'
            return httpx.Response(200,json={'status':'completed','output':[{'type':'function_call','call_id':'call-1','name':'get_world_rule','arguments':'{"rule_ids":["tick.order"]}'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            llm=LLMClient(Settings(llm_api_key='TEST'),client)
            result=await llm.complete([{'role':'user','content':'analyze'}],[],Deadline(1))
            assert result['tool_calls'][0]['id']=='call-1'
            await llm.complete([result,{'role':'tool','tool_call_id':'call-1','content':'rule data'}],[],Deadline(1))
            assert seen[1]['input'][0]['type']=='function_call'
            assert seen[1]['input'][1]['type']=='function_call_output'
            assert not seen[1]['store']
    asyncio.run(run())
