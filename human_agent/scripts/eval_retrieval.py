if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import argparse
import asyncio
import json
from app.world_rules import ROOT
from app.settings import Settings
from app.providers import Deadline
from app.retriever import Retriever

CASES=[
    ('energy','nominal human food energy consumed 3054 kcal 12.778 MJ',['3054','12.778']),
    ('water','nominal potable water content 3.217',['3.217']),
    ('oxygen','nominal human oxygen consumed 0.895 kg per crewmember',['0.895']),
    ('activity','reference astronaut 30 minutes aerobic 60 minutes resistive exercise',['30','60','exercise']),
    ('drinking_definition','drinking water food rehydration potable water definition',['rehydration','drinking']),
    ('zh_energy','太空人活動時的每日熱量需求基準',['energy','calor']),
    ('zh_water','太空人喝水與食物用水有什麼差異',['water','food']),
    ('no_evidence','quasar boson entanglement spectroscopy',[]),
    ('world_water','遊戲製水是否是物理守恆',['water_production.conversion']),
    ('world_death','個人能量歸零規則',['crew.personal.death'])
]

async def main(mode):
    s=Settings.load(); s.retrieval_mode=mode; s.retrieval_fallback='bm25' if mode=='dense' else 'none'
    r=Retriever(s); results=[]
    for case,query,terms in CASES:
        docs,info=await r.retrieve(query,5,Deadline(30))
        joined=' '.join(d['excerpt'].lower() for d in docs)
        if case.startswith('world_'): passed=bool(docs) and docs[0]['rule_id']==terms[0]
        elif not terms: passed=not docs
        else: passed=any(term.lower() in joined for term in terms)
        if not case.startswith('world_') and info['actual_mode'] not in ({'dense','mixed'} if mode=='dense' else {'bm25'}): passed=False
        result={'id':case,'query':query,'passed':passed,'actual_mode':info['actual_mode'],'fallback_reason':info['fallback_reason'],
                'evidence_ids':[d['id'] for d in docs], 'locators':[d['locator'] for d in docs]}
        results.append(result); print(case+': '+str(passed)+' ('+info['actual_mode']+')',flush=True)
    report={'mode':mode,'corpus_version':r.metadata.get('corpus_version'),'index_version':r.index_metadata.get('index_version'),
            'passed':sum(x['passed'] for x in results),'total':len(results),'method':'Configured retrieval: dense+BM25 fusion with exact numeric anchors, or BM25; top-5 original-text term presence and rule routing, not general entailment certification.','results':results}
    (ROOT/'docs'/('retrieval_eval_'+mode+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['passed']==len(results) else 2

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['dense','bm25'],default='bm25'); args=p.parse_args()
    raise SystemExit(asyncio.run(main(args.mode)))
