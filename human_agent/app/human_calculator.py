from collections import Counter
from math import ceil
from app.world_rules import F, RULES as R, RULES_HASH, ENERGY, WATER, OXYGEN, get_world_rule, json_numbers
from app.plan_auditor import audit_next_tick, current_failures
from app.unit_conversions import eu_to_kwh, conversion_evidence

def horizon(stock,rate,assumptions=None):
    common={'continuous_margin_ticks':None,'first_fatal_tick_offset':None,'safe_complete_ticks':None,'assumptions':assumptions or []}
    if stock is None or rate is None:
        return dict(common,status='unknown',assumptions=common['assumptions']+['Stock or requested work is unknown.'])
    if stock<=0:
        return dict(common,status='already_failed',continuous_margin_ticks=0,first_fatal_tick_offset=0,safe_complete_ticks=0)
    margin=F(stock)/F(rate)
    return dict(common,status='known',continuous_margin_ticks=margin,first_fatal_tick_offset=ceil(margin),safe_complete_ticks=max(0,ceil(margin)-1))

def analyze_baseline(s):
    audit=audit_next_tick(s); failures=current_failures(s)
    inconsistent=any(c.alive and (c.food_energy==0 or c.water==0) for c in s.crew) or (s.resources.oxygen==0 and any(c.alive for c in s.crew))
    missing=[]
    for k,v in s.resources.model_dump().items():
        if v is None: missing.append('resources.'+k)
    for c in s.crew:
        for k in ['food_energy','water','alive']:
            if getattr(c,k) is None: missing.append('crew.'+c.id+'.'+k)
    if s.next_tick_plan is None: missing.append('next_tick_plan')
    if s.plots is None: missing.append('plots')
    if s.water_production_available is None: missing.append('water_production_available')
    out={'schema_version':'2.0','request_id':s.request_id,'state_id':s.state_id,'tick':s.tick,'for_tick':s.tick+1,
         'world_rules_version':'0.12','rules_hash':RULES_HASH,
         'analysis_status':'partial' if missing or (audit and audit['status']=='incomplete') else 'complete',
         'execution_mode':'deterministic','current_world_condition':'already_failed' if failures else ('unknown' if any(x.startswith(('resources.','crew.')) for x in missing) else 'active'),
         'crew_assessments':[],'public_resource_assessment':{},'workforce_summary':{},'next_tick_audit':audit,
         'risks':[],'recommendations':[],'human_requests_to_core':[],'evidence':get_world_rule(list(R['rule_ids']))+[conversion_evidence()],
         'retrieval':{'requested_mode':'dense','actual_mode':'not_used','fallback_reason':None,'model':None,'dimensions':None},
         'corpus_version':None,'index_version':None,'research_status':'partial',
         'assumptions':['No-refill horizons are individual consumption references, not whole-world survival predictions.',
                        'Plans refer to the next unsettled tick even when paused. No real state is changed.',
                        'Personal horizons assume a living crew; aggregate reference rates assume four living crew. Unknown alive is never a verified survival assessment.'],
         'warnings':['Snapshot alive/status conflicts with a current terminal condition.'] if inconsistent else [],
         'missing_fields':missing,'integration_gaps':['Core/world production DTO mapping and fatal-phase micro-order require team alignment.', 'LAN connectivity has not been established by this calculation.'],
         'diagnostics':{'llm_calls':0,'embedding_calls':0,'cache_hits':0,'elapsed_ms':0},'tool_trace':[]}
    def risk(severity,domain,entity,resource,phase,description,rules,values=None):
        out['risks'].append({'id':'risk-'+str(len(out['risks'])+1),'severity':severity,'impact_domain':domain,'entity_id':entity,'resource':resource,'phase':phase,'tick_offset':0 if phase=='current' else 1,'description':description,'rule_ids':rules,'evidence_ids':[],'trigger_values':values or {}})
    tasks={} if s.next_tick_plan is None else {t.crew_id:t for t in s.next_tick_plan.crew_tasks}
    stages=audit['stage_results'] if audit else {}
    all_fatal=failures+(audit['fatal_conditions'] if audit and audit['fatal_stage']!='current' else [])
    for c in s.crew:
        task=tasks.get(c.id); work=None if task is None else (task.work_fraction if task.task=='generate' else 0)
        requested_rate=None if work is None else ENERGY+F(R['generation']['energy'])*F(work)
        low={k:None if getattr(c,k) is None else getattr(c,k)<R['crew'][k]['threshold'] for k in ['food_energy','water']}
        def after(stage):
            values=stages.get(stage,{}).get('details',{}).get('crew_after')
            return values.get(c.id) if values else None
        out['crew_assessments'].append({'crew_id':c.id,'alive':c.alive,'food_energy':c.food_energy,'water':c.water,
            'energy_ratio':None if c.food_energy is None else F(c.food_energy)/R['crew']['food_energy']['capacity'],
            'water_ratio':None if c.water is None else F(c.water)/R['crew']['water']['capacity'],'low_flags':low,
            'idle_no_refill':{'energy':horizon(c.food_energy,ENERGY,['Idle, no refill.']),'water':horizon(c.water,WATER,['No drinking.']),'energy_rate':ENERGY,'water_rate':WATER},
            'requested_work_no_refill':{'energy':horizon(c.food_energy,requested_rate,['Fixed requested work each tick, shared oxygen/power headroom sufficient; hypothetical.']), 'water':horizon(c.water,WATER,['No drinking; generation adds no extra water demand.']),'energy_rate':requested_rate,'water_rate':WATER},
            'after_refill':after('refill'),'after_base':after('base'),
            'actual_work':stages.get('generation',{}).get('details',{}).get('actual_work',{}).get(c.id),
            'fatal_conditions':[f for f in all_fatal if f['entity_id'] in {c.id,'all_crew','world'}]})
        for key in low:
            if low[key]: risk('warning','human',c.id,key,'current','Personal stock below low threshold.',['crew.personal.death'])
        if c.food_energy is not None and c.water is not None and F(c.food_energy)<=ENERGY and F(c.water)<=WATER:
            risk('critical','human',c.id,'food_energy_and_water','base','No feasible refill within this action space: one crew cannot eat and drink in the same tick.',['crew.task.exclusive','crew.personal.death'])
        if any(low.values()) and not failures:
            out['human_requests_to_core'].append({'crew_id':c.id,'request':'review_refill_and_work','low_flags':low,'coordination_needed':bool(task and task.task in {'plant','harvest','clear'}),'approved':False})
    for f in all_fatal:
        risk('critical','public' if f['entity_id']=='all_crew' else 'human',f['entity_id'],f['resource'],f['phase'],'Current failure or known fatal consumption; later production cannot rescue this phase.',f['rule_ids'],f['trigger_values'])
    for key,cfg in R['resources'].items():
        stock=getattr(s.resources,key)
        status='unknown' if stock is None else 'low' if stock<cfg['threshold'] else 'at_threshold' if stock==cfg['threshold'] else 'normal'
        out['public_resource_assessment'][key]={'stock':stock,'capacity':cfg['capacity'],'threshold':cfg['threshold'],'unit':cfg['unit'],'status':status}
        if status=='low': risk('warning','public','public',key,'current','Public threshold is advisory, not a reserve.',['public.threshold'])
    out['public_resource_assessment']['base_demand_per_tick']={'food_energy':ENERGY*4,'personal_water':WATER*4,'public_oxygen':OXYGEN*4}
    out['public_resource_assessment']['power']['energy_equivalent']={'kwh':None if s.resources.power is None else eu_to_kwh(s.resources.power),
        'kwh_per_eu':eu_to_kwh(1),'source':'unit_conversion.eu_kwh'}
    out['public_resource_assessment']['oxygen_respiration_only']=horizon(s.resources.oxygen,OXYGEN*4,['Respiration only; excludes generation, water production and plant oxygen.'])
    live_plots=None if s.plots is None else [p for p in s.plots if p.status in {'growing','mature'}]
    pressure=None
    if live_plots is not None:
        water=F(R['plant']['water'])*len(live_plots); power=F(R['plant']['power'])*len(live_plots)
        pressure={'active_plots':len(live_plots),'full_supply_water':water,'full_supply_power':power,
                  'full_supply_oxygen':sum(R['crops'][p.crop_type]['oxygen'] for p in live_plots),
                  'steady_rate_reference':{'water_production_liters':water+4*WATER,'plant_plus_water_power':power+(water+4*WATER)*F(R['water_production']['power']),
                                           'assumption':'Average replacement including personal base water; not actual discrete drinking or a schedule.'}}
    out['public_resource_assessment']['plant_supply_pressure']=pressure
    counts=None if not tasks else dict(Counter(t.task for t in tasks.values()))
    generation=stages.get('generation',{}).get('details',{})
    out['workforce_summary']={'task_counts':counts,'refill_occupied':None if counts is None else sum(counts.get(k,0) for k in ['eat','drink']),
        'crop_occupied':None if counts is None else sum(counts.get(k,0) for k in ['plant','harvest','clear']),
        'generation_requested_crew':None if counts is None else counts.get('generate',0),
        'requested_total_work':None if counts is None else sum(t.work_fraction for t in tasks.values() if t.task=='generate'),
        'requested_generation_upper_bound_eu':None if counts is None else sum(t.work_fraction for t in tasks.values() if t.task=='generate')*R['generation']['power'],
        'actual_total_work':generation.get('total_work'),'actual_power_produced':generation.get('power_produced'),
        'one_tick_all_crew_upper_bound_eu':R['crew_count']*R['generation']['power'],'assumption':'Upper bound only; excludes occupation and shared resource constraints.'}
    if counts and sum(counts.get(k,0) for k in ['eat','drink','plant','harvest','clear']):
        risk('warning','human',None,None,'generation','Refill/crop occupation reduces available generators.',['crew.task.exclusive'])
    for pid,info in stages.get('irrigation',{}).get('details',{}).get('plots',{}).items():
        if info['will_die']:
            risk('critical','plant_dependency',pid,'irrigation','irrigation','Third failed supply reaches plant death before crop operations.',['plant.irrigation.atomic'])
        elif info['reason']=='insufficient_allocation_or_stock':
            second=info['consecutive_unirrigated_ticks']==2
            risk('critical' if second else 'warning','plant_dependency',pid,'irrigation','irrigation',
                 'Second consecutive failed supply: plant is critical but has not reached death.' if second else 'No growth or oxygen this tick; failed irrigation counter increases.',
                 ['plant.irrigation.atomic'],{'consecutive_unirrigated_ticks':info['consecutive_unirrigated_ticks']})
    for plot in s.plots or []:
        if plot.status in {'growing','mature'} and plot.consecutive_unirrigated_ticks==2:
            risk('critical','plant_dependency',plot.id,'irrigation','current','Plant already has two consecutive failed supplies; another failure will kill it.',
                 ['plant.irrigation.atomic'],{'consecutive_unirrigated_ticks':2})
    water_info=stages.get('water_production',{}).get('details',{})
    if water_info.get('limited'): risk('warning','public','public','water','water_production','Water production request limited by availability, resources or capacity.',['water_production.conversion'])
    if missing or (audit and audit['unknown_dependencies']):
        risk('unknown','integration',None,None,'next_tick','Incomplete dependencies; no automatic plan or irrigation allocation assumed.',['tick.order'])
    return json_numbers(out)
