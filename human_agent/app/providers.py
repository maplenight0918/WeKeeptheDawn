"""Cancellable HTTP adapters. Error messages never include URLs, bodies or credentials."""
import asyncio
import json
import time
from collections import OrderedDict
from contextvars import ContextVar
import httpx
import numpy as np
from app.world_rules import digest

REQUEST_METRICS = ContextVar('human_request_metrics', default=None)

def record_metric(name):
    metrics = REQUEST_METRICS.get()
    if metrics is not None:
        metrics[name] = metrics.get(name, 0) + 1

class ProviderError(RuntimeError):
    pass

class Deadline:
    def __init__(self, seconds): self.end=time.monotonic()+seconds
    def remaining(self):
        remaining=self.end-time.monotonic()
        if remaining<=0: raise ProviderError('analysis_deadline_exceeded')
        return remaining

async def post_json(url, key, payload, timeout, deadline, client=None):
    if not key: raise ProviderError('missing_api_key')
    own=client is None
    client=client or httpx.AsyncClient(follow_redirects=False)
    try:
        for attempt in range(3):
            budget=min(timeout,deadline.remaining())
            try:
                async with asyncio.timeout(budget):
                    response=await client.post(url,headers={'Authorization':'Bearer '+key},json=payload,timeout=budget)
            except (TimeoutError,httpx.TimeoutException):
                raise ProviderError('provider_timeout') from None
            except httpx.HTTPError:
                raise ProviderError('provider_connection_error') from None
            if response.status_code==429 or 500<=response.status_code<600:
                if attempt<2 and deadline.remaining()>0.5*(attempt+1):
                    await asyncio.sleep(0.25*(attempt+1)); continue
            if response.status_code>=300:
                raise ProviderError('provider_http_'+str(response.status_code))
            try: return response.json()
            except ValueError: raise ProviderError('provider_invalid_json') from None
        raise ProviderError('provider_retry_exhausted')
    finally:
        if own: await client.aclose()

class EmbeddingClient:
    def __init__(self, settings, client=None):
        self.settings=settings; self.client=client; self.calls=0; self.cache_hits=0; self.query_cache=OrderedDict()

    @property
    def identity(self):
        s=self.settings
        return {'provider':s.embedding_provider,'model':s.embedding_model,'dimensions':s.embedding_dimensions,
                'policy':s.embedding_input_type_policy,'preprocessing_version':'original-paragraphs-v1'}

    def cache_key(self,text,kind='document'):
        return digest({**self.identity,'text_hash':digest(text),'kind':kind})

    def validate_vectors(self,vectors,count):
        try: array=np.asarray(vectors,dtype=np.float32)
        except (ValueError,TypeError): raise ProviderError('embedding_invalid_vectors') from None
        if array.shape!=(count,self.settings.embedding_dimensions) or not np.isfinite(array).all():
            raise ProviderError('embedding_count_dimensions_or_finite_mismatch')
        norms=np.linalg.norm(array,axis=1)
        if not np.isfinite(norms).all() or np.any(norms<=0): raise ProviderError('embedding_zero_or_invalid_norm')
        return array/norms[:,None]

    async def _embed(self,texts,kind,deadline):
        s=self.settings
        if any(len(t)>24000 for t in texts): raise ProviderError('embedding_input_too_long_rechunk_required')
        payload={'model':s.embedding_model,'input':texts,'encoding_format':'float'}
        if s.embedding_provider=='voyage':
            payload.update(input_type=kind,output_dimension=s.embedding_dimensions,truncation=False)
        else:
            payload['dimensions']=s.embedding_dimensions
        self.calls+=1
        record_metric('embedding_calls')
        response=await post_json(s.embedding_base_url.rstrip('/')+'/embeddings',s.embedding_api_key,payload,s.embedding_timeout_seconds,deadline,self.client)
        try:
            data=response['data']
            if len(data)!=len(texts) or {row['index'] for row in data}!=set(range(len(texts))):
                raise ProviderError('embedding_index_mapping_invalid')
            return self.validate_vectors([row['embedding'] for row in sorted(data,key=lambda x:x['index'])],len(texts))
        except (KeyError,TypeError,ValueError): raise ProviderError('embedding_response_invalid') from None

    async def embed_documents(self,texts,deadline): return await self._embed(texts,'document',deadline)
    async def embed_query(self,text,deadline):
        key=self.cache_key(text,'query')
        if key in self.query_cache:
            record_metric('cache_hits')
            self.cache_hits+=1; self.query_cache.move_to_end(key); return self.query_cache[key].copy()
        vector=(await self._embed([text],'query',deadline))[0]
        self.query_cache[key]=vector
        if len(self.query_cache)>256: self.query_cache.popitem(last=False)
        return vector.copy()

class LLMClient:
    def __init__(self,settings,client=None): self.settings=settings; self.client=client; self.calls=0

    async def complete(self,messages,tools,deadline):
        s=self.settings
        if not s.llm_model: raise ProviderError('missing_llm_model')
        self.calls+=1
        payload={'model':s.llm_model,'messages':messages,'tools':tools,'tool_choice':'auto','max_completion_tokens':2200}
        if not tools:
            payload.pop('tools'); payload.pop('tool_choice')
        # Astra tool calling uses Responses. OpenRouter retains its chat-compatible protocol.
        from urllib.parse import urlparse
        if s.llm_provider=='openai_compatible' and urlparse(s.llm_base_url).hostname=='api.openai.com':
            inputs=[]
            for message in messages:
                if message['role']=='tool':
                    inputs.append({'type':'function_call_output','call_id':message['tool_call_id'],'output':message['content']})
                    continue
                if message.get('content'):
                    inputs.append({'role':message['role'],'content':message['content']})
                for call in message.get('tool_calls') or []:
                    inputs.append({'type':'function_call','call_id':call['id'],'name':call['function']['name'],'arguments':call['function']['arguments']})
            payload={'model':s.llm_model,'input':inputs,'max_output_tokens':2200,'store':False}
            if tools:
                payload['tools']=[{'type':'function',**t['function'],'strict':False} for t in tools]
                payload['tool_choice']='auto'
            data=await post_json(s.llm_base_url.rstrip('/')+'/responses',s.llm_api_key,payload,s.llm_timeout_seconds,deadline,self.client)
            if data.get('status') not in {None,'completed'}: raise ProviderError('llm_response_incomplete')
            calls=[]; texts=[]
            for item in data.get('output',[]):
                if item.get('type')=='function_call':
                    calls.append({'id':item['call_id'],'type':'function','function':{'name':item['name'],'arguments':item['arguments']}})
                elif item.get('type')=='message':
                    texts.extend(c['text'] for c in item.get('content',[]) if c.get('type')=='output_text')
            return {'role':'assistant','content':'\n'.join(texts) or None,'tool_calls':calls}
        data=await post_json(s.llm_base_url.rstrip('/')+'/chat/completions',s.llm_api_key,payload,s.llm_timeout_seconds,deadline,self.client)
        try: return data['choices'][0]['message']
        except (KeyError,TypeError,IndexError): raise ProviderError('llm_response_invalid') from None
