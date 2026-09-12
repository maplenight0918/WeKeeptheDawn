if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import json
from app.main import app
from app.schemas import AnalyzeRequest,AnalyzeResponse
from app.discussion_types import DiscussionRequest,DiscussionReply
from app.world_rules import ROOT

for name,model in [('request',AnalyzeRequest),('response',AnalyzeResponse)]:
    (ROOT/'docs'/('human_api_2.0_'+name+'.schema.json')).write_text(json.dumps(model.model_json_schema(),indent=2),encoding='utf-8')
(ROOT/'docs/openapi.json').write_text(json.dumps(app.openapi(),indent=2),encoding='utf-8')
for name,model in [('request',DiscussionRequest),('response',DiscussionReply)]:
    (ROOT/'docs'/('core_discussion_1.3_'+name+'.schema.json')).write_text(json.dumps(model.model_json_schema(),indent=2),encoding='utf-8')
print('Exported request/response JSON Schema and OpenAPI.')
