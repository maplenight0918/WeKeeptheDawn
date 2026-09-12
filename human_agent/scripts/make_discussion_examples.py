"""Build reproducible Core-envelope manual cases from existing world fixtures."""
if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import copy
import json
from app.world_rules import ROOT
from app.discussion_types import DiscussionRequest

def make():
    folder=ROOT/'examples/discussion_requests'
    base=json.loads((folder/'with_plan.json').read_text(encoding='utf-8'))
    cases={}
    for name in ['critical','oxygen_early','refill_competition','irrigation_third_failure']:
        request=copy.deepcopy(base)
        human=json.loads((ROOT/'examples/requests'/(name+'.json')).read_text(encoding='utf-8'))
        for key in ['tick','resources','crew','plots','water_production_available','next_tick_plan']:
            request['content']['world'][key]=human[key]
        request['content']['question']='請分析此情境的人員與公共資源風險、原計畫可行性，以及需要 Core 協調的事項。'
        cases[name]=request
    second=copy.deepcopy(cases['irrigation_third_failure'])
    second['content']['world']['plots'][0]['consecutive_unirrigated_ticks']=1
    cases['irrigation_second_failure']=second
    current=copy.deepcopy(base)
    current['content']['world']['current_plan']=current['content']['world'].pop('next_tick_plan')
    cases['current_plan']=current
    dead=copy.deepcopy(base); dead['content']['world']['crew'][0]['alive']=False
    cases['already_failed']=dead
    for name,request in cases.items():
        request.update(message_id='core-test-'+name,discussion_id='discussion-test-'+name)
        request['content']['world']['world_status']='planning'
        request['display_text']='Human 人工測試：'+name
        request['explanation']['observations']=[]
        request['explanation']['proposals']=[]
        request['explanation']['decision_reason']='本機測試資料，尚未執行世界操作。'
        DiscussionRequest.model_validate(request)
        (folder/(name+'.json')).write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Created '+str(len(cases))+' Core discussion test cases.')

if __name__=='__main__': make()
