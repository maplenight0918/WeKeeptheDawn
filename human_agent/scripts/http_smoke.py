if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import httpx
from app.world_rules import ROOT
from app.schemas import AnalyzeResponse
from app.human_calculator import analyze_baseline
from app.schemas import AnalyzeRequest
from concurrent.futures import ThreadPoolExecutor

FIXTURES=['normal','critical','oxygen_early','refill_competition','irrigation_third_failure','partial']

def validate_result(name,payload,data,mode):
    AnalyzeResponse.model_validate(data)
    assert data['request_id']==payload['request_id'] and data['state_id']==payload['state_id'] and data['tick']==payload['tick']
    baseline=analyze_baseline(AnalyzeRequest.model_validate(payload))
    for field in ['crew_assessments','public_resource_assessment','workforce_summary','next_tick_audit','risks','current_world_condition']:
        assert data[field]==baseline[field], 'LLM altered deterministic field: '+field
    assert data['execution_mode']==mode, data['warnings']
    assert data['diagnostics']['elapsed_ms']<45000
    assert any(t['tool']=='retrieve_evidence' for t in data['tool_trace'])
    if name=='normal' and mode=='live': assert any(r['audit_result_id'] for r in data['recommendations'])
    if name in {'critical','oxygen_early'}: assert data['next_tick_audit']['fatal_stage']=='base'
    if name=='partial':
        assert data['analysis_status']=='partial' and data['next_tick_audit'] is None
        assert all(r['feasibility']!='verified_for_audited_scope' for r in data['recommendations'])
    if name=='irrigation_third_failure': assert any(r['severity']=='critical' and r['impact_domain']=='plant_dependency' for r in data['risks'])
    ids={e['id'] for e in data['evidence']}
    for rec in data['recommendations']:
        assert set(rec['evidence_ids'])<=ids and set(rec['rule_ids'])<=ids
    return True

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--live',action='store_true')
    parser.add_argument('--all',action='store_true'); parser.add_argument('--fixture',choices=FIXTURES)
    parser.add_argument('--concurrent',action='store_true',help='Two concurrent normal HTTP requests with different snapshot IDs')
    args=parser.parse_args()
    mode='live' if args.live else 'mock'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env={**os.environ,'AGENT_MODE':mode}
    process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    output=ROOT/'examples'/('live_responses' if args.live else 'responses'); output.mkdir(exist_ok=True)
    try:
        with httpx.Client(timeout=60) as client:
            url='http://127.0.0.1:'+str(port)
            for _ in range(100):
                try:
                    health=client.get(url+'/health'); health.raise_for_status(); break
                except httpx.HTTPError:
                    if process.poll() is not None: raise RuntimeError('Server startup failed; inspect configuration')
                    time.sleep(0.1)
            else: raise RuntimeError('Server startup timeout')
            (output/'health.json').write_text(json.dumps(health.json(),indent=2),encoding='utf-8')
            names=[args.fixture] if args.fixture else (FIXTURES if args.all or not args.live else ['normal'])
            reports=[]
            def request_fixture(name,suffix=''):
                payload=json.loads((ROOT/'examples/requests'/(name+'.json')).read_text(encoding='utf-8'))
                if suffix:
                    payload['request_id']+=suffix; payload['state_id']+=suffix
                response=client.post(url+'/human-agent/analyze',json=payload); response.raise_for_status(); data=response.json()
                (output/(name+suffix+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                try:
                    validate_result(name,payload,data,mode); passed=True; failure=None
                except (AssertionError,ValueError) as error:
                    passed=False; failure=type(error).__name__
                report={'fixture':name,'http_status':response.status_code,'execution_mode':data['execution_mode'],
                        'request_id':data['request_id'],'state_id':data['state_id'],'passed':passed,'validation_error':failure,
                        'retrieval':data['retrieval'],'diagnostics':data['diagnostics'],
                        'tool_names':[t['tool'] for t in data['tool_trace']],
                        'audited_proposals':sum(r['audit_result_id'] is not None for r in data['recommendations']),
                        'warnings':data['warnings']}
                print(json.dumps(report,ensure_ascii=True),flush=True)
                return report
            if args.concurrent:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(request_fixture,'normal','-concurrent-'+str(i)) for i in range(2)]
                    reports=[f.result() for f in futures]
            else:
                for name in names: reports.append(request_fixture(name))
            invalid=json.loads((ROOT/'examples/requests/normal.json').read_text(encoding='utf-8')); invalid['schema_version']='1.0'
            assert client.post(url+'/human-agent/analyze',json=invalid).status_code==422
            assert client.post(url+'/human-agent/analyze',content='{',headers={'Content-Type':'application/json'}).status_code==422
            assert client.get(url+'/openapi.json').status_code==200
            label='_concurrent' if args.concurrent else '_all' if len(names)>1 else '_'+names[0]
            (ROOT/'docs'/('http_validation_'+mode+label+'.json')).write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
            return 0 if all(r['passed'] for r in reports) else 2
    finally:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()

if __name__=='__main__': raise SystemExit(main())
