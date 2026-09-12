import copy
import json
from fractions import Fraction
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.schemas import AnalyzeRequest, AnalyzeResponse
from app.world_rules import F, ENERGY, WATER, OXYGEN
from app.human_calculator import analyze_baseline, horizon
from app.plan_auditor import audit_next_tick, generate_stage, water_stage
from app.main import create_app
from app.settings import Settings

def audit(raw): return audit_next_tick(AnalyzeRequest.model_validate(raw))
def idle(raw):
    raw['next_tick_plan']['crew_tasks']=[{'crew_id':c['id'],'task':'idle'} for c in raw['crew']]
    raw['next_tick_plan']['water_production_request_liters']=0

def test_t01_exact_base():
    assert ENERGY*4==509 and WATER*4==F('3.217')/6 and OXYGEN*4==F(895)/6

def test_t02_idle_margin():
    assert horizon(2400,ENERGY)['first_fatal_tick_offset']==19
    assert horizon(2400,ENERGY)['safe_complete_ticks']==18
    assert horizon(1.5,WATER)['first_fatal_tick_offset']==12
    assert horizon(1.5,WATER)['safe_complete_ticks']==11

def test_t03_work_margin():
    assert ENERGY+100==F('227.25')
    assert horizon(2400,ENERGY+100)['first_fatal_tick_offset']==11

def test_t04_exact_zero_boundary():
    assert horizon(254.5,ENERGY)['first_fatal_tick_offset']==2
    assert horizon(254.5,ENERGY)['safe_complete_ticks']==1

def test_t05_transfer_conservation(raw):
    idle(raw); raw['crew'][0]['food_energy']=2900; raw['resources']['food']=50
    raw['next_tick_plan']['crew_tasks'][0]={'crew_id':'crew-1','task':'eat','amount':1000}; raw['next_tick_plan']['refill_order']=['crew-1']
    a=audit(raw); stages=a['stage_results']
    assert stages['refill']['details']['transfers'][0]['actual']==50
    assert stages['refill']['details']['crew_after']['crew-1']['food_energy']==2950
    assert stages['base']['details']['crew_after']['crew-1']['food_energy']==2822.75
    assert stages['generation']['details']['actual_work']['crew-1']==0
    assert a['known_after_values']['public_resources']['food']==0

def test_t06_refill_order(raw):
    idle(raw); raw['resources']['food']=1000
    for i in range(2):
        raw['crew'][i]['food_energy']=500
        raw['next_tick_plan']['crew_tasks'][i]={'crew_id':'crew-'+str(i+1),'task':'eat','amount':1000}
    for order in [['crew-1','crew-2'],['crew-2','crew-1']]:
        raw['next_tick_plan']['refill_order']=order
        transfers=audit(raw)['stage_results']['refill']['details']['transfers']
        assert [(t['crew_id'],t['actual']) for t in transfers]==[(order[0],1000),(order[1],0)]

@pytest.mark.parametrize('task',['eat','harvest'])
def test_t07_duplicate_tasks_422(raw,task):
    raw['next_tick_plan']['crew_tasks'][1]['crew_id']='crew-1'
    with TestClient(create_app(Settings())) as client: assert client.post('/human-agent/analyze',json=raw).status_code==422

@pytest.mark.parametrize('task,amount',[('eat',1000),('drink',0.5)])
def test_t08_dual_refill_impossible(raw,task,amount):
    raw['crew'][0].update(food_energy=100,water=0.1)
    raw['next_tick_plan']['crew_tasks'][0]={'crew_id':'crew-1','task':task,'amount':amount}; raw['next_tick_plan']['refill_order']=['crew-1']
    assert audit(raw)['fatal_stage']=='base'
    assert any('No feasible refill' in r['description'] for r in analyze_baseline(AnalyzeRequest.model_validate(raw))['risks'])

def test_t09_respiration_zero(raw):
    raw['resources']['oxygen']=float(F(895)/6)
    a=audit(raw); assert a['fatal_stage']=='base'
    assert all(a['stage_results'][k]['status']=='not_reached' for k in ['generation','water_production','irrigation'])
    assert a['known_after_values'] is None

def test_t10_generation_exhausts_personal(raw):
    raw['crew'][0]['food_energy']=177.25
    a=audit(raw); assert a['fatal_stage']=='generation'
    assert a['stage_results']['generation']['details']['actual_work']['crew-1']==0.5
    assert a['known_after_values'] is None

def test_t11_battery_shared_cap(raw):
    raw['resources']['power']=9750
    a=audit(raw)['stage_results']['generation']['details']
    assert a['total_work']==1 and set(a['actual_work'].values())=={0.25}

def test_t12_proportional_stage_start(snapshot):
    tasks={t.crew_id:t for t in snapshot.next_tick_plan.crew_tasks}
    tasks['crew-3'].work_fraction=0; tasks['crew-4'].work_fraction=0
    crew={c.id:{'food_energy':F(1000)} for c in snapshot.crew}; crew['crew-2']['food_energy']=F(50)
    a,total,work=generate_stage(crew,{'oxygen':F(1000),'power':F(9850)},tasks)
    assert total==F('0.6') and work['crew-1']==F('0.4') and work['crew-2']==F('0.2')

def test_t13_water_stage_start():
    assert water_stage(174,{'water':F(3000),'power':F(6000),'oxygen':F(8000)},True)==174

def test_t14_water_capacity_and_oxygen_stage():
    actual=water_stage(300,{'water':F(3990),'power':F(100),'oxygen':F(2)},True)
    assert actual==10 and 2-actual*F('0.2')==0

def test_t15_no_future_water_credit(raw):
    raw['resources']['water']=0; raw['crew'][0]['water']=0.1
    raw['next_tick_plan']['crew_tasks'][0]={'crew_id':'crew-1','task':'drink','amount':0.5}; raw['next_tick_plan']['refill_order']=['crew-1']
    a=audit(raw); assert a['stage_results']['refill']['details']['transfers'][0]['actual']==0
    assert a['fatal_stage']=='base'

def test_t16_public_food_zero_not_death(raw):
    raw['resources']['food']=0
    assert audit(raw)['status']=='feasible_in_scope'

def test_t17_full_irrigation(raw):
    a=audit(raw)['stage_results']['irrigation']['details']
    assert (a['water_used'],a['power_used'],a['oxygen_produced'])==(174,100,304)

@pytest.mark.parametrize('water,power',[(8.7,0),(0,0)])
def test_t18_atomic_irrigation(raw,water,power):
    raw['next_tick_plan']['irrigation_allocations']=[{'plot_id':'plot-1','water_quota_liters':water,'power_quota_eu':power}]
    d=audit(raw)['stage_results']['irrigation']['details']; assert d['water_used']==d['power_used']==0
    assert d['plots']['plot-1']['consecutive_unirrigated_ticks']==1

def test_t19_mature_third_failure_and_recovery(raw):
    raw['plots'][0].update(status='mature',growth_ticks=30,consecutive_unirrigated_ticks=2)
    assert audit(raw)['stage_results']['irrigation']['details']['plots']['plot-1']['consecutive_unirrigated_ticks']==0
    raw['next_tick_plan']['irrigation_allocations']=[]
    assert audit(raw)['stage_results']['irrigation']['details']['plots']['plot-1']['will_die']
    assert any(r['severity']=='critical' and r['impact_domain']=='plant_dependency' for r in analyze_baseline(AnalyzeRequest.model_validate(raw))['risks'])

def test_t20_oxygen_overflow(raw):
    idle(raw); raw['resources']['oxygen']=15000
    a=audit(raw); assert a['known_after_values']['public_resources']['oxygen']==15000
    assert a['stage_results']['irrigation']['details']['oxygen_overflow']==pytest.approx(304-895/6)

def test_t21_partial_no_automatic_policy(raw):
    raw.update(next_tick_plan=None,plots=None); raw['resources']['food']=None
    b=analyze_baseline(AnalyzeRequest.model_validate(raw)); assert b['analysis_status']=='partial' and b['next_tick_audit'] is None
    assert b['crew_assessments'][0]['idle_no_refill']['energy']['status']=='known'
    assert b['crew_assessments'][0]['requested_work_no_refill']['energy']['status']=='unknown'

@pytest.mark.parametrize('status',['paused','planning','error_paused'])
def test_t22_read_only_repeatable(raw,status):
    raw['world_status']=status; s=AnalyzeRequest.model_validate(raw); before=s.model_dump()
    assert analyze_baseline(s)==analyze_baseline(s) and s.model_dump()==before

@pytest.mark.parametrize('failure',['dead','zero','failed'])
def test_t23_current_failure(raw,failure):
    if failure=='dead': raw['crew'][0]['alive']=False
    if failure=='zero': raw['crew'][0]['food_energy']=0
    if failure=='failed': raw['world_status']='failed'
    b=analyze_baseline(AnalyzeRequest.model_validate(raw)); assert b['current_world_condition']=='already_failed' and b['next_tick_audit']['status']=='not_applicable'

@pytest.mark.parametrize('case',['version','oxygen_kg','negative','nan','infinity','rules','tick','plot_count','unknown_crew','extra_payload','duplicate_refill'])
def test_t24_validation(raw,case):
    if case=='version': raw['schema_version']='1.0'
    if case=='oxygen_kg': raw['resources']['oxygen_kg']=1
    if case=='negative': raw['resources']['water']=-1
    if case=='nan': raw['resources']['water']=float('nan')
    if case=='infinity': raw['resources']['water']=float('inf')
    if case=='rules': raw['world_rules_version']='0.11'
    if case=='tick': raw['next_tick_plan']['for_tick']=2
    if case=='plot_count': raw['plots']=[]
    if case=='unknown_crew': raw['next_tick_plan']['crew_tasks'][0]['crew_id']='other'
    if case=='extra_payload': raw['next_tick_plan']['crew_tasks'][0]['amount']=50
    if case=='duplicate_refill': raw['next_tick_plan']['refill_order']=['crew-1','crew-1']
    with pytest.raises(ValidationError): AnalyzeRequest.model_validate(raw)

def test_t28_response_openapi_http(raw):
    with TestClient(create_app(Settings())) as client:
        response=client.post('/human-agent/analyze',json=raw)
        assert response.status_code==200
        AnalyzeResponse.model_validate(response.json())
        assert 'AnalyzeResponse' in client.get('/openapi.json').json()['components']['schemas']
        assert 'Infinity' not in response.text and 'NaN' not in response.text
        assert client.get('/health').json()['provider_connectivity']=='not_probed'

def test_t29_full_numeric_accounting(raw):
    a=audit(raw); assert a['status']=='feasible_in_scope' and a['coverage_end']=='after_irrigation_before_crop_operations'
    values=a['known_after_values']; public=values['public_resources']
    assert public==pytest.approx({'water':3000,'food':120000,'power':6552,'oxygen':8020.033333333333})
    for crew in values['crew'].values():
        assert crew['food_energy']==2172.75 and crew['water']==pytest.approx(1.5-3.217/24)

def test_unknown_device_stops_dependency_chain(raw):
    raw['water_production_available']=None
    a=audit(raw); assert a['status']=='incomplete' and a['stage_results']['water_production']['status']=='unknown'
    assert a['stage_results']['irrigation']['status']=='unknown'

def test_unknown_base_still_reports_independent_fatal(raw):
    raw['crew'][0]['food_energy']=None; raw['crew'][1]['water']=0.01
    a=audit(raw); assert a['fatal_stage']=='base' and any(f['entity_id']=='crew-2' for f in a['fatal_conditions'])

def test_threshold_equality_not_reserve(raw):
    raw['resources']['water']=400
    b=analyze_baseline(AnalyzeRequest.model_validate(raw)); assert b['public_resource_assessment']['water']['status']=='at_threshold'
