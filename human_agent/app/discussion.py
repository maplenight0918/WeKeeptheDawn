"""Explicit translation between the Core discussion protocol and Human accounting."""
import math
import uuid
import json
from fastapi import HTTPException
from app.discussion_types import DiscussionContext, DiscussionReply, DiscussionSnapshot
from app.schemas import AnalyzeRequest
from app.world_rules import RULES as R, ROOT, ENERGY, WATER, OXYGEN, digest
from app.unit_conversions import EU_TO_KWH, eu_to_kwh, conversion_context
from app.core_compat import compatible_schema, read_core_plan

CORE_RULES_VERSION = 'greenhouse-2026-09-12-v1'
EXPLANATION_SCHEMA=json.loads((ROOT/'data/core_explanation_v1.3.schema.json').read_text(encoding='utf-8'))

def expected_core_rules():
    return {
        'rules_version': CORE_RULES_VERSION, 'tick_hours': R['tick_hours'],
        'environment': {'carbon_dioxide': {'value': R['plant']['background']['co2_ppm'], 'unit': 'ppm', 'adjustable': False}},
        'resources': {k: {'unit': v['unit'], 'capacity': v['capacity'], 'warning': v['threshold']} for k,v in R['resources'].items()},
        'crew': {
            'daily_reference': {'kcal': float(R['crew']['daily_energy']), 'water_L': float(R['crew']['daily_water']), 'oxygen_kg': float(R['crew']['daily_oxygen_kg'])},
            'per_tick': {'food_energy': float(ENERGY), 'water': float(WATER), 'oxygen': float(OXYGEN)},
            'capacity': {k: R['crew'][k]['capacity'] for k in ['food_energy','water']},
            'warning': {k: R['crew'][k]['threshold'] for k in ['food_energy','water']},
            'refill_limit': {'eat': R['crew']['food_energy']['refill_max'], 'drink': R['crew']['water']['refill_max']},
            'refill_ratio': 1,
            'death': 'personal energy or water <= 0; any crew death ends mission'},
        'generation': {'food_energy': R['generation']['energy'], 'oxygen': R['generation']['oxygen'], 'power': R['generation']['power'], 'max_units_per_crew_tick': 1, 'stations': R['crew_count']},
        'water_production': {'power_per_L': R['water_production']['power'], 'oxygen_per_L': R['water_production']['oxygen'], 'max_L_per_tick': R['water_production']['limit']},
        'irrigation': {'water_per_plot': R['plant']['water'], 'power_per_plot': R['plant']['power'], 'atomic_inputs': True, 'misses_until_death': R['plant']['death_unirrigated_ticks'],
            'priority': 'Core supplied order; omitted living plots receive nothing',
            'failure': 'no input deducted, no growth or oxygen; success resets misses',
            'dead': 'no consumption or yield; clear before planting'},
        'crops': {k: {'maturity_ticks':v['maturity_ticks'], 'harvest_game_kcal':v['harvest'], 'oxygen_per_tick':v['oxygen']} for k,v in R['crops'].items()},
        'tasks': {'occupancy': 'eat, drink, generate, plant, harvest, clear: one crew per tick', 'controls_and_movement': 'visual only, no occupancy',
            'crop_actions': 'at tick end, ordered; no premature harvest; full storage blocks harvest', 'plant': 'empty plot only; no seed cost; starts growing next tick'},
        'oxygen_death': 'public oxygen <= 0 immediately kills all crew, even before plants produce oxygen',
        'tick_order': ['ordered refill','personal metabolism','public breathing','generation','water production','ordered irrigation','ordered crop actions'],
        'planning': 'world paused while planning; validate state version before apply; no simulator',
        'completion': 'no stable/success threshold; continue until death'}

def rule_mismatches(actual, expected=None, path='content.rules'):
    expected = expected_core_rules() if expected is None else expected
    if path in {'content.rules.planning','content.rules.rules_version'}:
        return [] if isinstance(actual,str) and actual.strip() else [path]
    if isinstance(expected, dict):
        if not isinstance(actual, dict): return [path]
        metadata={'title','description','notes','metadata','source','$comment'}
        errors=[]
        for key in actual.keys()-expected.keys()-metadata:
            if key in {'eu_to_kwh','kwh_per_eu'} and path in {'content.rules','content.rules.resources.power'}:
                value=actual[key]
                if type(value) not in {int,float} or value!=float(EU_TO_KWH): errors.append(path+'.'+key)
            else: errors.append(path+'.'+key)
        for k,v in expected.items():
            errors.extend([path+'.'+k] if k not in actual else rule_mismatches(actual[k],v,path+'.'+k))
        return sorted(errors)
    if isinstance(expected, (float,int)) and not isinstance(expected,bool):
        valid = type(actual) in {float,int} and math.isfinite(actual)
        if valid:
            # Wire-format rounding tolerance only for derived rates, never for stocks or death checks.
            valid = math.isclose(actual,expected,rel_tol=1e-12,abs_tol=0) if '.per_tick.' in path else actual==expected
    elif isinstance(expected,str) and not path.endswith('.unit'):
        valid=isinstance(actual,str) and bool(actual.strip())
    else:
        valid = type(actual) is type(expected) and actual==expected
    return [] if valid else [path]

def changed_rule_descriptions(actual,expected=None,path='content.rules'):
    expected=expected_core_rules() if expected is None else expected
    if isinstance(expected,dict):
        return [item for k,v in expected.items() for item in changed_rule_descriptions(actual[k],v,path+'.'+k)]
    if isinstance(expected,str) and not path.endswith(('.unit','.rules_version','.planning')):
        if ' '.join(actual.lower().split())!=' '.join(expected.lower().split()): return [path]
    return []

def map_discussion(request):
    content=request.content; world=content.world
    errors=rule_mismatches(content.rules)
    if world.rules_version != content.rules.get('rules_version'): errors.append('content.world.rules_version')
    if errors:
        raise HTTPException(409,detail={'error':'rules_mismatch','fields':errors})
    if request.world_version != world.world_version:
        raise HTTPException(409,detail={'error':'world_version_mismatch'})
    if not compatible_schema(content.explanation_schema,EXPLANATION_SCHEMA):
        raise HTTPException(409,detail={'error':'explanation_schema_mismatch'})
    if set(content.analysis_scope) != {'water','oxygen','power','food'}:
        raise HTTPException(422,detail={'error':'human_analysis_scope_required'})
    references=set(); message_ids=set()
    for message in content.previous_messages:
        valid=(message.get('discussion_id')==request.discussion_id and
               type(message.get('world_version')) is int and message['world_version']==request.world_version and
               type(message.get('round')) is int and 1<=message['round']<request.round and
               message.get('sender') in {'core','plant','human'} and
               isinstance(message.get('message_id'),str) and bool(message['message_id'].strip()) and
               message['message_id'] not in message_ids and message['message_id']!=request.message_id)
        if not valid: raise HTTPException(409,detail={'error':'history_identity_mismatch'})
        message_ids.add(message['message_id'])
        explanation=message.get('explanation')
        if not isinstance(explanation,dict) or not isinstance(explanation.get('proposals'),list):
            raise HTTPException(422,detail={'error':'invalid_history_proposals'})
        for p in explanation['proposals']:
            if not isinstance(p,dict) or not isinstance(p.get('proposal_id'),str) or not p['proposal_id'].strip():
                raise HTTPException(422,detail={'error':'invalid_history_proposals'})
            key=(message['message_id'],p['proposal_id'])
            if key in references: raise HTTPException(422,detail={'error':'duplicate_history_proposal'})
            references.add(key)
    if request.round>1 and not content.previous_messages:
        raise HTTPException(422,detail={'error':'follow_up_requires_history'})
    plan,adapter_unknowns,raw_plan=read_core_plan(world,content)
    changed_descriptions=changed_rule_descriptions(content.rules)
    if changed_descriptions:
        adapter_unknowns.append('規則說明文字已變更，數值相容但執行語意尚未核對：'+', '.join(changed_descriptions)+'；暫不驗證完整計畫可行性。')
    snapshot=DiscussionSnapshot.model_validate({
        'schema_version':'2.0','request_id':request.message_id,
        'state_id':'core-'+digest({'discussion_id':request.discussion_id,'world_version':request.world_version}),
        'world_rules_version':'0.12','tick':world.tick,'snapshot_phase':world.snapshot_phase,
        'world_status':world.world_status,'resources':world.resources.model_dump(),
        'crew':[c.model_dump() for c in world.crew], 'plots':[p.model_dump() for p in world.plots],
        'water_production_available':world.water_production_available,
        'next_tick_plan':None if plan is None else plan.model_dump(), 'rules_semantics_known':not changed_descriptions})
    context=DiscussionContext(payload={
        'discussion_id':request.discussion_id,'round':request.round,'world_version':request.world_version,
        'question':content.question,'follow_up_reason':request.explanation.follow_up_reason,
        'initial_reason':content.reason,'previous_messages':content.previous_messages,
        'response_guidance':content.response_guidance,'unit_conversion_policy':content.unit_conversion_policy,
        'analysis_scope':content.analysis_scope,'core_explanation':request.explanation.model_dump(),
        'adapter_uncertainties':adapter_unknowns,'provided_plan':raw_plan,
        'core_rules':content.rules,'unit_conversion':conversion_context()},references=references)
    return snapshot,context

STRATEGIES={
    'eat':'請 Core 檢視進食安排，將公共食物轉入個人能量。',
    'drink':'請 Core 檢視飲水安排，將當階段可用公共水轉入個人。',
    'adjust_generation':'請 Core 檢視候選發電工作量。',
    'adjust_water_production':'請 Core 檢視候選製水量。',
    'reserve_crew_for_refill':'請 Core 協調人員的吃喝補給與工作占用。',
    'request_plant_review':'請 Core 與 Plant 協調作物供應及工作安排。'}

def make_reply(request, result, context):
    r=result.model_dump(); message_id='human-'+uuid.uuid4().hex
    observations=[]
    for c in r['crew_assessments']:
        life='存活未知' if c['alive'] is None else ('存活' if c['alive'] else '已死亡')
        observations.append(f"{c['crew_id']}：{life}，個人能量 {c['food_energy']:g} 遊戲 kcal，水 {c['water']:g} L。")
    for k,v in r['public_resource_assessment'].items():
        if isinstance(v,dict) and 'stock' in v:
            observations.append(f"公共 {k}：{v['stock']:g} {v['unit']}，庫存標示 {v['status']}。")
    for risk in r['risks']:
        observations.append(f"風險 {risk['severity']}：對象 {risk['entity_id'] or '整體'}，項目 {risk['resource'] or risk['impact_domain']}，階段 {risk['phase']}；依據 {', '.join(risk['rule_ids'])}。")
    uncertainties=['僅有單 tick 規則算術預檢，沒有未來 Simulator，也沒有執行世界操作。',
        '規則數值已對照本機 world v0.12；共享發電比例及死亡微順序仍需與世界後端整合驗證。',
        '科學文獻尚未全面逐項審閱；已檢索不等於已證明建議。',
        'decision_reason 與 reviews 是模型公開評估；量化效果只以候選核算結果為準。']
    if r['missing_fields']: uncertainties.append('缺少核算資料：'+', '.join(r['missing_fields'])+'；相關結果不推定。')
    uncertainties.extend(context.payload['adapter_uncertainties'])
    if r['execution_mode']=='mock': uncertainties.append('目前是 mock 測試回覆，未呼叫遠端 LLM。')
    if r['current_world_condition']=='already_failed':
        observations.insert(0,'當前世界已符合任務失敗條件，不能復活或產生可執行救援方案。')
    if r['next_tick_audit']:
        a=r['next_tick_audit']
        observations.append('原計畫預檢狀態：'+a['status']+'；unsafe_in_scope 表示已知植物死亡等不安全結果，並非全員死亡；incomplete 表示核算依據不足。')
    proposals=[]; actions=[]
    tradeoffs=['進食、飲水與作物工作會占用人員；部分發電仍不能同 tick 兼做其他工作。',
               '降低發電量可減少額外能量與氧氣消耗，也會減少電力產出。']
    for i,rec in enumerate(r['recommendations'],1):
        pid=message_id+'-p'+str(i)
        evidence=['world v0.12 規則 '+rid for rid in rec['rule_ids']]
        evidence.extend(e['title']+'；'+e['locator']+'；'+str(e['source_url']) for e in r['evidence'] if e['id'] in rec['evidence_ids'])
        effect='尚無完整候選核算，不宣稱量化效果。'
        if rec['expected_effect']:
            audit=rec['expected_effect']['candidate_audit']
            effect='候選的單 tick 算術預檢為 '+rec['feasibility']+'，不是世界試跑。'
            if audit['known_after_values']:
                p=audit['known_after_values']['public_resources']
                effect+=' 灌溉後、作物操作前公共庫存：'+', '.join(k+'='+str(v) for k,v in p.items())+'。'
        proposals.append({'proposal_id':pid,'strategy':STRATEGIES[rec['proposal_kind']],
            'reason':'依目前個人與公共資源、工作占用及固定世界規則提出，交由 Core 比較原計畫後決策。',
            'expected_effect':effect,'tradeoffs':tradeoffs,'evidence':evidence})
        actions.append({'proposal_id':pid,'description':STRATEGIES[rec['proposal_kind']],
            'proposal_kind':rec['proposal_kind'],'target_crew_ids':rec['target_crew_ids'],
            'proposed_changes':rec['proposed_changes'],'feasibility':rec['feasibility'],
            'audit_result_id':rec['audit_result_id'],'expected_effect':rec['expected_effect'],
            'requires_core_approval':True})
    notes=context.notes
    answer=notes.answer if notes else '已完成固定世界規則分析，請 Core 依風險與缺少資料決定下一步。'
    reviews=[] if notes is None else [v.model_dump() for v in notes.reviews]
    if notes: uncertainties.extend(notes.uncertainties)
    # Do not convert a model review into a claim of an audited or executed world plan.
    if reviews: uncertainties.append('reviews 是模型對公開提案的評估；不代表完整計畫已經核算或核准。')
    status='當前世界已失敗，不能復活' if r['current_world_condition']=='already_failed' else ('發現需優先處理的危急風險' if any(x['severity']=='critical' for x in r['risks']) else '已完成個人與公共資源分析')
    summary='本輪提供 '+str(len(proposals))+' 項供 Core 審核的建議' if not proposals else '建議重點：'+'；'.join(p['strategy'].rstrip('。') for p in proposals)
    audited=r['next_tick_audit']
    scope='未提供完整下一 tick 計畫，先回覆狀態與需求分析。' if not audited else ('缺少核算依據，尚未驗證具體安排可行。' if audited['status']=='incomplete' else '已有單 tick 算術預檢，仍由 Core 決策。')
    display=f"{status}。{summary}。"+scope
    evidence=['world v0.12 rules_hash='+r['rules_hash'],
        'Core rules_version='+request.content.world.rules_version,
        '使用者確認換算：1 EU = 3.9745 kWh = 3974.5 Wh；來源 unit_conversion.eu_kwh，非 NASA 認證，不改遊戲係數。',
        f"公共電力 {request.content.world.resources.power:g} EU 對應 {float(eu_to_kwh(request.content.world.resources.power)):g} kWh。",
        f"執行模式 {r['execution_mode']}；耗時 {r['diagnostics']['elapsed_ms']} ms；LLM 呼叫 {r['diagnostics']['llm_calls']} 次。"]
    if notes:
        evidence.extend('world v0.12 規則 '+rid for rid in notes.rule_ids)
        evidence.extend(e['title']+'；'+e['locator']+'；'+str(e['source_url']) for e in r['evidence'] if e['id'] in notes.evidence_ids)
    explanation={'observations':observations,'proposals':proposals,'reviews':reviews,
        'conflicts':[] if notes is None else notes.conflicts,
        'follow_up_reason':'如需驗證具體計畫，需釐清上述未知資料；一般討論可繼續。' if audited and audited['status']=='incomplete' else '',
        'decision_reason':answer,'uncertainties':uncertainties}
    return DiscussionReply.model_validate({'message_id':message_id,'discussion_id':request.discussion_id,
        'round':request.round,'world_version':request.world_version,'display_text':display,
        'explanation':explanation,'content':{'observations':observations,
        'priorities':['優先處理人員存活、吃喝補給與公共氧氣，再比較工作和供水用電。'],
        'suggested_actions':actions,'acceptable_tradeoffs':tradeoffs,'evidence_and_unknowns':evidence+uncertainties}})
