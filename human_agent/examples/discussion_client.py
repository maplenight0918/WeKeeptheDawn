"""Standalone HTTP client for the agreed Core discussion contract; no app imports."""
import argparse
import copy
import json
import os
import sys
import time
import uuid
from pathlib import Path
import httpx
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]

def validate_reply(reply,request):
    expected={'discussion_id':request['discussion_id'],'round':request['round'],
              'world_version':request['world_version'],'sender':'human','recipient':'core'}
    if any(type(reply.get(k)) is not type(v) or reply[k]!=v for k,v in expected.items()):
        raise ValueError('Mismatched discussion identity')
    history=request['content']['previous_messages']
    mid=reply.get('message_id')
    if not isinstance(mid,str) or not mid or mid in {request['message_id'],*(m['message_id'] for m in history)}:
        raise ValueError('Missing or reused reply message ID')
    public=[p['proposal_id'] for p in reply['explanation']['proposals']]
    actions=[p['proposal_id'] for p in reply['content']['suggested_actions']]
    if len(set(public))!=len(public) or actions!=public:
        raise ValueError('Content/explanation proposal IDs do not match')
    refs={(m['message_id'],p['proposal_id']) for m in history for p in m['explanation']['proposals']}
    reviewed=[(r['message_id'],r['proposal_id']) for r in reply['explanation']['reviews']]
    if len(reviewed)!=len(set(reviewed)) or not set(reviewed)<=refs:
        raise ValueError('Unresolvable review reference')

def follow_up(request,reply,question):
    validate_reply(reply,request)
    if request['round']>=3: raise ValueError('Core contract permits at most three rounds')
    next_request=copy.deepcopy(request)
    next_request.update(round=request['round']+1,message_id='core-manual-'+uuid.uuid4().hex)
    next_request['content']['previous_messages'].append(copy.deepcopy(reply))
    next_request['content']['question']=question
    next_request['explanation']['follow_up_reason']=question
    return next_request

def main():
    parser=argparse.ArgumentParser(description='Send JSON to a running Human /discuss service and save replies.')
    source=parser.add_mutually_exclusive_group()
    source.add_argument('--fixture',default='core_original_human')
    source.add_argument('--request',type=Path)
    parser.add_argument('--url'); parser.add_argument('--rounds',type=int,choices=[1,2,3],default=1)
    parser.add_argument('--question',help='Override the first question')
    parser.add_argument('--follow-up-question',default='請回顧前輪提案與未知事項，說明應保留或修改哪些建議；若有提案請提供對應 reviews，勿假設已執行。')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'examples/manual_discussion_responses')
    args=parser.parse_args()
    values={**dotenv_values(ROOT/'.env'),**os.environ}
    url=(args.url or values.get('HUMAN_AGENT_URL') or 'http://127.0.0.1:8000').rstrip('/')
    path=args.request or ROOT/'examples/discussion_requests'/(args.fixture+'.json')
    request=json.loads(path.read_text(encoding='utf-8'))
    if request['round']+args.rounds-1>3: parser.error('The final round must not exceed 3')
    if args.question: request['content']['question']=args.question
    output=args.output_dir/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]); output.mkdir(parents=True)
    with httpx.Client(timeout=45) as client:
        for _ in range(args.rounds):
            number=request['round']
            (output/f'round{number}.request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
            began=time.perf_counter()
            response=client.post(url+'/discuss',json=request)
            elapsed=round(time.perf_counter()-began,3)
            (output/f'round{number}.metrics.json').write_text(json.dumps({'http_status':response.status_code,'client_elapsed_seconds':elapsed},indent=2),encoding='utf-8')
            reply=response.json()
            (output/f'round{number}.response.json').write_text(json.dumps(reply,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Round {number}: HTTP {response.status_code}, {elapsed} s',flush=True)
            if not response.is_success:
                print('Request failed; inspect the saved error response. Output: '+str(output))
                return 1
            validate_reply(reply,request)
            print(reply['display_text']); print(reply['explanation']['decision_reason'])
            if _+1<args.rounds: request=follow_up(request,reply,args.follow_up_question)
    print('Saved requests and replies: '+str(output))
    return 0

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    try: raise SystemExit(main())
    except (httpx.HTTPError,OSError,ValueError,KeyError,TypeError) as exc:
        print('Manual test failed: '+type(exc).__name__+'. Check the running server, JSON file and saved response.')
        raise SystemExit(1)
