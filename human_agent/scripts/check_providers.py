if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import asyncio
import json
from app.settings import Settings, ConfigurationError
from app.providers import Deadline, EmbeddingClient, LLMClient, ProviderError

async def main():
    s=Settings.load(); results={}; deadline=Deadline(43)
    for name in ['embedding','llm']:
        try:
            if name=='embedding':
                vector=await EmbeddingClient(s).embed_query('astronaut potable water requirements',deadline)
                results[name]={'status':'ok','dimensions':len(vector)}
            else:
                llm=LLMClient(s)
                response=await llm.complete([{'role':'user','content':'Reply with JSON {"ok":true}.'}],[],deadline)
                if not response.get('content'): raise ProviderError('empty_llm_output')
                results[name]={'status':'ok','model':s.llm_model}
        except ProviderError as e: results[name]={'status':'failed','reason':str(e)}
    print(json.dumps(results)); return 0 if all(x['status']=='ok' for x in results.values()) else 2

if __name__=='__main__':
    try: code=asyncio.run(main())
    except ConfigurationError as e: print(str(e)); code=2
    raise SystemExit(code)
