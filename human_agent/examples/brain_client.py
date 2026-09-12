"""Standalone Core-side HTTP consumer. Does not import the Human app."""
import argparse
import json
import os
from pathlib import Path
import httpx
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]

def map_core_snapshot(core):
    """Explicit example mapping, not an assumed production world contract."""
    return {'schema_version':'2.0','request_id':core['request_id'],'state_id':core['snapshot_id'],
            'world_rules_version':'0.12','tick':core['tick'],'snapshot_phase':'between_ticks',
            'world_status':core['status'],'resources':core['public_resources'],'crew':core['people'],
            'plots':core.get('plots'),'water_production_available':core.get('water_device_available'),
            'next_tick_plan':core.get('proposed_next_tick'),'analysis':{'include_recommendations':True}}

def analyze(client,url,snapshot):
    response=client.post(url.rstrip('/')+'/human-agent/analyze',json=snapshot)
    response.raise_for_status(); data=response.json()
    validate_response_identity(data,snapshot)
    return data

def validate_response_identity(data,snapshot):
    expected={'schema_version':'2.0','world_rules_version':snapshot['world_rules_version'],
              'request_id':snapshot['request_id'],'state_id':snapshot['state_id'],
              'tick':snapshot['tick'],'for_tick':snapshot['tick']+1}
    if any(data.get(key)!=value for key,value in expected.items()):
        raise ValueError('Reject mismatched/stale response')

def response_is_current(data,latest_state_id,latest_tick):
    """Core must call this again immediately before adopting a proposal."""
    return data.get('state_id')==latest_state_id and data.get('tick')==latest_tick and data.get('for_tick')==latest_tick+1

def main():
    p=argparse.ArgumentParser(); p.add_argument('--all',action='store_true'); p.add_argument('--fixture',default='normal'); p.add_argument('--url'); p.add_argument('--output-dir',default='examples/manual_responses'); args=p.parse_args()
    values={**dotenv_values(ROOT/'.env'),**os.environ}; url=args.url or values.get('HUMAN_AGENT_URL','http://127.0.0.1:8000')
    names=sorted((ROOT/'examples/requests').glob('*.json')) if args.all else [ROOT/'examples/requests'/(args.fixture+'.json')]
    output=ROOT/args.output_dir; output.mkdir(parents=True,exist_ok=True)
    with httpx.Client(timeout=float(values.get('BRAIN_CLIENT_TIMEOUT_SECONDS',60))) as client:
        health=client.get(url.rstrip('/')+'/health'); health.raise_for_status(); print('health: '+health.json()['status'])
        for path in names:
            snapshot=json.loads(path.read_text(encoding='utf-8')); data=analyze(client,url,snapshot)
            (output/(path.stem+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            print(path.stem+': HTTP 200, '+data['execution_mode']+', '+data['analysis_status']+', critical='+str(sum(r['severity']=='critical' for r in data['risks']))+', output='+str(output/(path.stem+'.json')))
    return 0

if __name__=='__main__': raise SystemExit(main())
