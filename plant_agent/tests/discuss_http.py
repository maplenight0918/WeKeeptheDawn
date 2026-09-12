import json,time,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from src.api.discussion_schema import DiscussOutput
raw=json.loads(Path('tests/fixtures/discuss_round1.json').read_text(encoding='utf-8'))
aligned='--aligned' in sys.argv
if aligned:
    from src.agent.discussion import energy_summary
    raw['discussion_id']='aligned-power-test'
    raw['content']['rules']['irrigation']['power_per_plot']=energy_summary(1,1)['per_plot_EU_per_tick']
    raw['content']['unit_conversion_policy']='已確認1 EU=3.9745 kWh，每tick一小時。Plant沿用總功率乘24小時保守基準；無需再選公式，不能額外加扣舊5 EU。'
results=[]
for n in [1,2]:
    raw['round']=n
    raw['message_id']=f'core-network-test-{n}'
    if n==2:
        raw['content']['previous_messages']=[results[0]['body']]
        raw['content']['question']='請檢視你上一輪的建議，說明電力每tick按一小時計算時，請列出已定案Plant耗電與傳入舊規則的差異，勿再要求選公式或決定設備時數。'
        raw['explanation']['follow_up_reason']='已確認每塊5 m²、135株，電量以EU顯示且1 EU=3.9745 kWh。'
    if aligned and n==2:
        raw['content']['question']='請檢视上輪建議，確認目前Plant電力與rules已一致，提出水資源方面的具體建議並review上輪提案。'
    t=time.monotonic()
    req=Request('http://127.0.0.1:8000/discuss',data=json.dumps(raw).encode(),headers={'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=50) as response:
            status=response.status;body=json.load(response)
    except HTTPError as e:
        status=e.code;body=json.load(e)
    elapsed=time.monotonic()-t
    results.append({'round':n,'status':status,'seconds':elapsed,'body':body})
    Path('.tools/discuss-http-aligned.json' if aligned else '.tools/discuss-http-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results[-1],ensure_ascii=False),flush=True)
    assert status==200
    out=DiscussOutput.model_validate(body)
    assert out.round==n and out.world_version==raw['world_version'] and out.discussion_id==raw['discussion_id'] and out.message_id!=raw['message_id']
    assert elapsed<45

    assert any('4.166781 EU' in x for x in out.content.evidence_and_unknowns)
    if not aligned:
        assert any('100.000000 EU' in x and '4.166781 EU' in x for x in out.explanation.conflicts)
    if n==2:
        valid={(results[0]['body']['message_id'],p['proposal_id']) for p in results[0]['body']['explanation']['proposals']}
        assert out.explanation.reviews
        assert all((r.message_id,r.proposal_id) in valid for r in out.explanation.reviews)
