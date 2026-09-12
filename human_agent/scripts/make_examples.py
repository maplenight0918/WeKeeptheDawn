if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import copy
import json
from app.world_rules import ROOT, RULES as R

def normal():
    crew=[{'id':'crew-'+str(i),'alive':True,'food_energy':R['crew']['food_energy']['initial'],'water':R['crew']['water']['initial']} for i in range(1,5)]
    plots=[{'id':'plot-'+str(i+1),'status':'growing','crop_type':crop,'growth_ticks':0,'consecutive_unirrigated_ticks':0} for i,crop in enumerate([crop for crop in R['crops'] for _ in range(4)])]
    return {'schema_version':'2.0','request_id':'human-normal-001','state_id':'state-0-r1','world_rules_version':'0.12','tick':0,
            'snapshot_phase':'between_ticks','world_status':'paused','resources':{k:v['initial'] for k,v in R['resources'].items()},'crew':crew,
            'plots':plots,'water_production_available':True,'next_tick_plan':{'for_tick':1,'crew_tasks':[{'crew_id':c['id'],'task':'generate','work_fraction':1} for c in crew],
                'refill_order':[],'water_production_request_liters':174,
                'irrigation_allocations':[{'plot_id':p['id'],'water_quota_liters':8.7,'power_quota_eu':5} for p in plots], 'crop_operation_order':[]},
            'analysis':{'include_recommendations':True}}

def make():
    base=normal(); fixtures={'normal':base}
    critical=copy.deepcopy(base); critical['request_id']='human-critical-001'; critical['crew'][0].update(food_energy=100,water=0.1)
    critical['next_tick_plan']['crew_tasks'][0]={'crew_id':'crew-1','task':'eat','amount':1000}; critical['next_tick_plan']['refill_order']=['crew-1']; fixtures['critical']=critical
    oxygen=copy.deepcopy(base); oxygen['request_id']='human-oxygen-001'; oxygen['resources']['oxygen']=100; fixtures['oxygen_early']=oxygen
    competition=copy.deepcopy(base); competition['request_id']='human-refill-001'; competition['resources']['food']=1000
    for i in range(2):
        competition['crew'][i]['food_energy']=500
        competition['next_tick_plan']['crew_tasks'][i]={'crew_id':'crew-'+str(i+1),'task':'eat','amount':1000}
    competition['next_tick_plan']['refill_order']=['crew-2','crew-1']; fixtures['refill_competition']=competition
    irrigation=copy.deepcopy(base); irrigation['request_id']='human-irrigation-001'; irrigation['plots'][0]['consecutive_unirrigated_ticks']=2
    irrigation['next_tick_plan']['irrigation_allocations']=[]; fixtures['irrigation_third_failure']=irrigation
    partial=copy.deepcopy(base); partial['request_id']='human-partial-001'; partial.update(plots=None,water_production_available=None,next_tick_plan=None); fixtures['partial']=partial
    path=ROOT/'examples/requests'; path.mkdir(exist_ok=True)
    for name,value in fixtures.items(): (path/(name+'.json')).write_text(json.dumps(value,indent=2),encoding='utf-8')
    print('Created '+str(len(fixtures))+' schema 2.0 request fixtures.')

if __name__=='__main__': make()
