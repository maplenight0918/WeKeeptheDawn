"""Real localhost HTTP exercise of the Core envelope, including a follow-up round."""
if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import argparse
import copy
import json
import os
import socket
import subprocess
import sys
import time
import httpx
from app.world_rules import ROOT
from app.discussion_types import DiscussionReply

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--live',action='store_true')
    parser.add_argument('--all',action='store_true',help='Also exercise the seven standalone boundary/adapter cases')
    args=parser.parse_args()
    mode='live' if args.live else 'mock'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
        cwd=ROOT,env={**os.environ,'AGENT_MODE':mode},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    output=ROOT/'examples/discussion_responses'/mode; output.mkdir(parents=True,exist_ok=True)
    reports=[]
    try:
        with httpx.Client(base_url='http://127.0.0.1:'+str(port),timeout=50) as client:
            for _ in range(100):
                try:
                    client.get('/health').raise_for_status(); break
                except httpx.HTTPError:
                    if process.poll() is not None: raise RuntimeError('Server startup failed')
                    time.sleep(0.1)
            else: raise RuntimeError('Server startup timeout')
            original=json.loads((ROOT/'examples/discussion_requests/core_original_human.json').read_text(encoding='utf-8'))
            began=time.monotonic(); response=client.post('/discuss',json=original)
            elapsed=round((time.monotonic()-began)*1000,2)
            response.raise_for_status(); original_reply=response.json(); DiscussionReply.model_validate(original_reply)
            assert any('存活未知' in s for s in original_reply['content']['observations'])
            assert all(a.get('feasibility')!='verified_for_audited_scope' for a in original_reply['content']['suggested_actions'])
            assert elapsed<45000
            (output/'core_original.json').write_text(json.dumps(original_reply,ensure_ascii=False,indent=2),encoding='utf-8')
            report={'case':'original_core_request','http_status':response.status_code,'mode':mode,'client_elapsed_ms':elapsed,'passed':True}
            reports.append(report); print(json.dumps(report),flush=True)
            request=json.loads((ROOT/'examples/discussion_requests/with_plan.json').read_text(encoding='utf-8'))
            bad=copy.deepcopy(request); bad['content']['rules']['generation']['power']=125
            assert client.post('/discuss',json=bad).status_code==409
            for round_number in [1,2,3]:
                began=time.monotonic(); response=client.post('/discuss',json=request)
                elapsed=round((time.monotonic()-began)*1000,2)
                (output/f'round{round_number}.json').write_text(json.dumps(response.json(),ensure_ascii=False,indent=2),encoding='utf-8')
                response.raise_for_status(); reply=response.json(); DiscussionReply.model_validate(reply)
                assert reply['message_id']!=request['message_id']
                assert all(reply[k]==request[k] for k in ['discussion_id','round','world_version'])
                assert any('執行模式 '+mode in s for s in reply['content']['evidence_and_unknowns'])
                assert elapsed<45000
                refs={(m['message_id'],p['proposal_id']) for m in request['content']['previous_messages'] for p in m['explanation']['proposals']}
                assert all((r['message_id'],r['proposal_id']) in refs for r in reply['explanation']['reviews'])
                if args.live and round_number==1:
                    assert any(a.get('audit_result_id') for a in reply['content']['suggested_actions'])
                if round_number>1: assert reply['explanation']['reviews']
                report={'round':round_number,'http_status':response.status_code,'mode':mode,'client_elapsed_ms':elapsed,
                    'proposals':len(reply['explanation']['proposals']),'reviews':len(reply['explanation']['reviews']),'passed':True}
                reports.append(report); print(json.dumps(report),flush=True)
                if round_number==1:
                    request['round']=2; request['message_id']='core-request-human-002'
                    # Include a Plant message to test real cross-specialist references even in mock mode.
                    plant={'message_id':'plant-public-001','discussion_id':request['discussion_id'],'world_version':request['world_version'],
                        'round':1,'sender':'plant','recipient':'core','display_text':'請保留原定農地供應。',
                        'explanation':{'observations':[],'proposals':[{'proposal_id':'plant-keep-supply','strategy':'保留原定灌溉配額。',
                            'reason':'避免失灌。','expected_effect':'依既有配額供應，尚未執行。','tradeoffs':['需要公共水電。'],'evidence':['rules.irrigation']}],
                            'reviews':[],'conflicts':[],'follow_up_reason':'','decision_reason':'','uncertainties':[]},
                        'content':{'observations':[],'priorities':[],'suggested_actions':[],'acceptable_tradeoffs':[],'evidence_and_unknowns':[]}}
                    request['content']['previous_messages']=[reply,plant]
                    request['content']['question']='請評論前輪 Human 與 Plant 建議：降低發電比例後，是否代表同一人能在這個 tick 兼做飲水？請針對真實提案提供 reviews，說明工作占用限制，保留灌溉配額。'
                    request['explanation']['follow_up_reason']='Core 要釐清部分發電與飲水的占用衝突，Plant 要求維持灌溉。'
                    (output/'round2.request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
                elif round_number==2:
                    request['round']=3; request['message_id']='core-request-human-003'
                    request['content']['previous_messages'].append(reply)
                    request['content']['question']='請依前兩輪討論作最後評估，評論已有提案是否應保留，列出剩餘未知；不可推定世界已執行或人員可兼做任務。'
                    request['explanation']['follow_up_reason']='第三輪收斂，交由 Core 決策，不再要求第四輪。'
                    (output/'round3.request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
            if args.all:
                for name in ['current_plan','critical','oxygen_early','refill_competition','irrigation_second_failure','irrigation_third_failure','already_failed']:
                    payload=json.loads((ROOT/'examples/discussion_requests'/(name+'.json')).read_text(encoding='utf-8'))
                    began=time.monotonic(); response=client.post('/discuss',json=payload)
                    elapsed=round((time.monotonic()-began)*1000,2)
                    (output/(name+'.json')).write_text(json.dumps(response.json(),ensure_ascii=False,indent=2),encoding='utf-8')
                    response.raise_for_status(); reply=response.json(); DiscussionReply.model_validate(reply)
                    assert elapsed<45000
                    expected={'current_plan':'feasible_in_scope','critical':'fatal_in_scope','oxygen_early':'fatal_in_scope',
                              'refill_competition':'feasible_in_scope','irrigation_second_failure':'feasible_in_scope',
                              'irrigation_third_failure':'unsafe_in_scope','already_failed':'not_applicable'}[name]
                    assert any('原計畫預檢狀態：'+expected in s for s in reply['content']['observations'])
                    if name=='already_failed': assert not reply['content']['suggested_actions']
                    report={'case':name,'http_status':response.status_code,'mode':mode,'client_elapsed_ms':elapsed,'audit_status':expected,'passed':True}
                    reports.append(report); print(json.dumps(report),flush=True)
            assert client.get('/openapi.json').status_code==200
        (ROOT/'docs'/f'discussion_http_{mode}.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    finally:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()

if __name__=='__main__': main()
