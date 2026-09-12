import uuid
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Body
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.schemas import AnalyzeRequest, AnalyzeResponse
from app.settings import Settings
from app.world_rules import RULES_HASH, ROOT
from app.retriever import Retriever
from app.agent import HumanAgent
from app.discussion_types import DiscussionRequest, DiscussionReply
from app.discussion import map_discussion, make_reply
from fastapi import HTTPException
from pydantic import ValidationError

def create_app(settings=None,agent=None):
    discussion_examples={name:{'summary':label,'value':json.loads((ROOT/'examples/discussion_requests'/(name+'.json')).read_text(encoding='utf-8'))}
        for name,label in [('core_original_human','Core 原始請求：無計畫、存活未知'),('current_plan','正常：使用 current_plan 核算'),
                           ('critical','個人能量與水不足'),('oxygen_early','呼吸階段缺氧'),
                           ('irrigation_second_failure','第二次失灌：危急但尚未死亡'),('irrigation_third_failure','第三次失灌：植物死亡') ]}
    @asynccontextmanager
    async def lifespan(app):
        configured=settings or Settings.load()
        app.state.settings=configured
        app.state.agent=agent or HumanAgent(configured,Retriever(configured))
        yield
    app=FastAPI(title='Human Agent',version='2.0',lifespan=lifespan,description='Read-only world v0.12 analysis, never a world step API.')

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Do not echo invalid input or Pydantic context: either may contain secret-like user data.
        message=('Requires Core handoff v1.3. Optional alive stays unknown; snapshot_phase defaults to between_ticks and discussion world_status to planning. See docs/core_handoff_alignment.md.' if request.url.path=='/discuss' else 'Requires Human API schema 2.0, world 0.12, between_ticks snapshot and complete valid plan. See docs/api_migration.md.')
        return JSONResponse(status_code=422,content={'error':'schema_validation','message':message,
                'issues':[{'location':list(e['loc']),'type':e['type']} for e in exc.errors()]})

    @app.exception_handler(Exception)
    async def unexpected_error(request,exc):
        return JSONResponse(status_code=500,content={'error':'internal_error','request_id':getattr(request.state,'request_id',str(uuid.uuid4()))})

    @app.get('/health')
    async def health():
        s=app.state.settings; r=app.state.agent.retriever
        return {'status':'ok','schema_version':'2.0','world_rules_version':'0.12','rules_hash':RULES_HASH,
                'configured_mode':s.agent_mode,'missing_setting_names':s.missing(),'llm':{'provider':s.llm_provider,'model':s.llm_model},
                'embedding':{'provider':s.embedding_provider,'model':s.embedding_model,'dimensions':s.embedding_dimensions},
                'corpus_version':r.metadata.get('corpus_version'),'index_version':r.index_metadata.get('index_version'),
                'dense_loaded':r.vectors is not None,'bm25_loaded':r.bm25 is not None,'dense_issue':r.dense_error,
                'provider_connectivity':'not_probed'}

    @app.post('/human-agent/analyze',response_model=AnalyzeResponse)
    async def analyze(snapshot:AnalyzeRequest,request:Request):
        request.state.request_id=snapshot.request_id
        return await app.state.agent.analyze(snapshot)

    @app.post('/discuss',response_model=DiscussionReply)
    async def discuss(request:Request,message:DiscussionRequest=Body(openapi_examples=discussion_examples)):
        request.state.request_id=message.message_id
        try:
            snapshot,context=map_discussion(message)
        except ValidationError as exc:
            raise HTTPException(422,detail={'error':'invalid_human_snapshot','issues':[{'location':list(e['loc']),'type':e['type']} for e in exc.errors()]}) from None
        try:
            async with asyncio.timeout(44):
                result=await app.state.agent.analyze(snapshot,discussion=context)
        except TimeoutError:
            raise HTTPException(504,detail={'error':'analysis_deadline_exceeded','request_id':message.message_id}) from None
        if result.execution_mode=='degraded':
            # Core requires failures to be non-2xx. Preserve useful baseline inside the error,
            # but never publish degraded output as a successful specialist message.
            raise HTTPException(502,detail={'error':'specialist_analysis_failed','request_id':message.message_id,
                'baseline':{'analysis_status':result.analysis_status,'current_world_condition':result.current_world_condition,
                            'risks':[r.model_dump() for r in result.risks],'missing_fields':result.missing_fields}})
        return make_reply(message,result,context)
    return app

app=create_app()
