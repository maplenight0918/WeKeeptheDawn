"""Read-only single tick human preflight; deliberately stops before crop operations."""
from app.world_rules import F, RULES as R, ENERGY, WATER, OXYGEN, digest, json_numbers
from app.schemas import AnalyzeRequest, Plan

STAGES = ['refill','base','generation','water_production','irrigation','crop_operations']

def current_failures(s):
    failures = []
    for c in s.crew:
        if c.alive is False:
            failures.append(condition(c.id, 'alive', 'current', 0, 0, 'crew.personal.death'))
        for key in ['food_energy','water']:
            if getattr(c,key) == 0:
                failures.append(condition(c.id, key, 'current', 0, 0, 'crew.personal.death'))
    if s.resources.oxygen == 0:
        failures.append(condition('all_crew','oxygen','current',0,0,'world.oxygen.death'))
    if s.world_status == 'failed' and not failures:
        failures.append(condition('world','status','current',None,None,'crew.personal.death'))
    return failures

def condition(entity, resource, phase, stock, required, rule):
    return {'entity_id': entity, 'resource': resource, 'phase': phase,
            'trigger_values': {'stock': stock, 'required': required}, 'rule_ids': [rule]}

def generate_stage(crew, resources, tasks):
    g = R['generation']
    a = {cid: min(F(t.work_fraction), F(1), crew[cid]['food_energy']/g['energy']) if t.task == 'generate' else F(0) for cid,t in tasks.items()}
    A = sum(a.values(), F(0))
    W = min(A, resources['oxygen']/g['oxygen'], (R['resources']['power']['capacity']-resources['power'])/g['power'])
    work = {cid: F(0) if A == 0 else W*ai/A for cid,ai in a.items()}
    return a, W, work

def water_stage(requested, resources, available):
    if requested == 0 or available is False:
        return F(0)
    if available is None or any(resources[k] is None for k in ['water','power','oxygen']):
        return None
    w = R['water_production']
    return min(F(requested), F(w['limit']), resources['power']/F(w['power']), resources['oxygen']/F(w['oxygen']), F(R['resources']['water']['capacity'])-resources['water'])

def audit_next_tick(snapshot: AnalyzeRequest, plan: Plan | None = None):
    p = plan or snapshot.next_tick_plan
    if p is None:
        return None
    # Revalidate candidate with original state: no candidate can mutate snapshot inputs.
    snapshot = type(snapshot).model_validate({**snapshot.model_dump(), 'next_tick_plan': p.model_dump()})
    out = {'result_id': 'audit-'+digest({'state':snapshot.model_dump(),'plan':p.model_dump()})[:16],
           'status':'incomplete','scope':'hypothetical_single_tick_human_preflight', 'for_tick':p.for_tick,
           'coverage_end':None,'fatal_stage':None,
           'stage_results':{stage:{'status':'not_reached','details':{}} for stage in STAGES},
           'ledger':[], 'known_after_values':None,'fatal_conditions':[], 'unknown_dependencies':[],
           'limitations':['Read-only hypothetical accounting; never an authoritative world state.',
                           'Stops before crop operations; no harvest, planting, clock advance or future yield simulation.',
                           'Fatal phase micro-order is unspecified; no terminal complete state is published.']}
    resources = {k: None if v is None else F(v) for k,v in snapshot.resources.model_dump().items()}
    crew = {c.id:{'food_energy':None if c.food_energy is None else F(c.food_energy), 'water':None if c.water is None else F(c.water)} for c in snapshot.crew}
    tasks = {t.crew_id:t for t in p.crew_tasks}
    failures = current_failures(snapshot)
    if failures:
        out.update(status='not_applicable',fatal_stage='current',fatal_conditions=failures)
        return json_numbers(out)
    unknown_life=['crew.'+c.id+'.alive' for c in snapshot.crew if c.alive is None]
    unknown_rules=[] if getattr(snapshot,'rules_semantics_known',True) else ['rules.description_semantics']
    if unknown_life or unknown_rules:
        out['unknown_dependencies']=unknown_life+unknown_rules
        out['stage_results']={name:{'status':'unknown','details':{'reason':'Crew survival or rule semantics unknown; no transfers or future execution assumed.'}} for name in STAGES}
        return json_numbers(out)

    def stage(name, details, unknown=False):
        out['stage_results'][name] = {'status':'unknown' if unknown else 'evaluated','details':details}
        if not unknown:
            out['coverage_end'] = 'after_'+name

    def ledger(phase, kind, resource, entity, amount):
        out['ledger'].append(dict(phase=phase,kind=kind,resource=resource,entity_id=entity,amount=amount))

    def fatal(name, fatal_conditions):
        out.update(status='fatal_in_scope',fatal_stage=name,fatal_conditions=fatal_conditions)
        # Consumption in the fatal phase is not claimed as a committed ledger.
        out['ledger'] = [entry for entry in out['ledger'] if entry['phase'] != name]
        return json_numbers(out)

    transfers=[]
    for cid in p.refill_order:
        task=tasks[cid]
        personal, public = ('food_energy','food') if task.task=='eat' else ('water','water')
        cfg=R['crew'][personal]
        stock, local = resources[public],crew[cid][personal]
        actual = None if stock is None or local is None else min(F(task.amount),F(cfg['refill_max']),stock,F(cfg['capacity'])-local)
        transfers.append({'crew_id':cid,'resource':personal,'requested':task.amount,'actual':actual,
                          'capacity_limited':None if local is None else F(cfg['capacity'])-local < F(task.amount),
                          'stock_limited':None if stock is None else stock < F(task.amount)})
        if actual is None:
            crew[cid][personal]=None
            resources[public]=None
            out['unknown_dependencies'].append('refill.'+cid+'.'+personal)
        else:
            resources[public]-=actual
            crew[cid][personal]+=actual
            ledger('refill','transfer',public,cid,actual)
    stage('refill',{'transfers':transfers,'crew_after':{cid:dict(c) for cid,c in crew.items()}}, bool(out['unknown_dependencies']))

    failures=[]
    for cid,c in crew.items():
        for key,rate in [('food_energy',ENERGY),('water',WATER)]:
            stock=c[key]
            if stock is None:
                out['unknown_dependencies'].append('base.'+cid+'.'+key)
            elif stock <= rate:
                failures.append(condition(cid,key,'base',stock,rate,'crew.personal.death'))
                c[key]=None
            else:
                c[key]-=rate
                ledger('base','consumption',key,cid,rate)
    respiration=OXYGEN*R['crew_count']
    if resources['oxygen'] is None:
        out['unknown_dependencies'].append('base.public.oxygen')
    elif resources['oxygen'] <= respiration:
        failures.append(condition('all_crew','oxygen','base',resources['oxygen'],respiration,'world.oxygen.death'))
        resources['oxygen']=None
    else:
        resources['oxygen']-=respiration
        ledger('base','consumption','oxygen','public',respiration)
    stage('base',{'crew_after':None if failures else {cid:dict(c) for cid,c in crew.items()}, 'respiration':respiration,
                  'public_oxygen_after':None if failures else resources['oxygen'], 'fatal_conditions':failures},bool(out['unknown_dependencies']) and not failures)
    if failures:
        return fatal('base', failures)
    if out['unknown_dependencies']:
        for name in STAGES[2:]:
            stage(name,{'reason':'base survival not established'},True)
        return json_numbers(out)

    generators = [cid for cid,t in tasks.items() if t.task=='generate' and t.work_fraction > 0]
    if generators and resources['power'] is None:
        out['unknown_dependencies'].append('generation.public.power')
        for name in STAGES[2:]: stage(name,{'reason':'generation dependency unknown'},True)
        return json_numbers(out)
    if generators:
        a,total,work=generate_stage(crew,resources,tasks)
    else:
        a={cid:F(0) for cid in crew}; total=F(0); work=dict(a)
    g=R['generation']; failures=[]
    for cid,w in work.items():
        crew[cid]['food_energy']-=w*g['energy']
        if crew[cid]['food_energy']<=0:
            failures.append(condition(cid,'food_energy','generation',w*g['energy'],w*g['energy'],'crew.personal.death'))
        ledger('generation','consumption','food_energy',cid,w*g['energy'])
    resources['oxygen']-=g['oxygen']*total
    if resources['power'] is not None: resources['power']+=g['power']*total
    if resources['oxygen']<=0:
        failures.append(condition('all_crew','oxygen','generation',g['oxygen']*total,g['oxygen']*total,'world.oxygen.death'))
    ledger('generation','consumption','oxygen','public',g['oxygen']*total)
    ledger('generation','production','power','public',g['power']*total)
    stage('generation',{'eligible_work':a,'actual_work':work,'total_work':total,'power_produced':total*g['power'],'fatal_conditions':failures})
    if failures: return fatal('generation',failures)

    actual=water_stage(p.water_production_request_liters,resources,snapshot.water_production_available)
    if actual is None:
        out['unknown_dependencies'].append('water_production.availability_or_resources')
        for name in STAGES[3:]: stage(name,{'reason':'water production dependency unknown'},True)
        return json_numbers(out)
    w=R['water_production']
    if actual:
        resources['water']+=actual
        resources['power']-=F(w['power'])*actual
        resources['oxygen']-=F(w['oxygen'])*actual
        ledger('water_production','production','water','public',actual)
        ledger('water_production','consumption','power','public',F(w['power'])*actual)
        ledger('water_production','consumption','oxygen','public',F(w['oxygen'])*actual)
    stage('water_production',{'requested_liters':p.water_production_request_liters,'actual_liters':actual,
                              'limited':actual<F(p.water_production_request_liters),'availability':snapshot.water_production_available})
    if resources['oxygen']<=0:
        return fatal('water_production',[condition('all_crew','oxygen','water_production',actual*F(w['oxygen']),actual*F(w['oxygen']),'world.oxygen.death')])

    if snapshot.plots is None or p.irrigation_allocations is None:
        out['unknown_dependencies'].append('irrigation.plots_or_allocations')
        stage('irrigation',{'reason':'complete plots and explicit allocations required'},True)
        stage('crop_operations',{'reason':'world executes crop operations; prerequisites unknown'},True)
        return json_numbers(out)
    plots={plot.id:plot for plot in snapshot.plots}
    allocated={a.plot_id:a for a in p.irrigation_allocations}
    results={}; overflow=F(0); water_used=F(0); power_used=F(0); oxygen_produced=F(0)
    # Only allocated order drives spending. Unallocated plots never consume resources.
    order=[a.plot_id for a in p.irrigation_allocations]+[pid for pid in plots if pid not in allocated]
    for pid in order:
        plot=plots[pid]; quota=allocated.get(pid)
        if plot.status not in {'growing','mature'}:
            results[pid]={'supplied':False,'reason':'empty_or_dead','will_die':False,'consecutive_unirrigated_ticks':plot.consecutive_unirrigated_ticks}
            continue
        enough_quota=quota is not None and F(quota.water_quota_liters)>=F(R['plant']['water']) and F(quota.power_quota_eu)>=F(R['plant']['power'])
        enough_stock = all(resources[k] is not None and resources[k]>=F(R['plant'][k]) for k in ['water','power'])
        known_short = any(resources[k] is not None and resources[k]<F(R['plant'][k]) for k in ['water','power'])
        if enough_quota and not enough_stock and not known_short:
            results[pid]={'supplied':None,'reason':'public_stock_unknown','will_die':None,'consecutive_unirrigated_ticks':None}
            out['unknown_dependencies'].append('irrigation.'+pid)
            # Unknown earlier spending contaminates shared stocks for later allocations.
            resources['water']=resources['power']=resources['oxygen']=None
            continue
        success=enough_quota and enough_stock
        counter=0 if success else plot.consecutive_unirrigated_ticks+1
        results[pid]={'supplied':success,'reason':'full_supply' if success else 'insufficient_allocation_or_stock',
                      'will_die':counter>=R['plant']['death_unirrigated_ticks'],'consecutive_unirrigated_ticks':counter}
        if success:
            water_used+=F(R['plant']['water']); power_used+=F(R['plant']['power'])
            resources['water']-=F(R['plant']['water']); resources['power']-=F(R['plant']['power'])
            oxygen=F(R['crops'][plot.crop_type]['oxygen']); oxygen_produced+=oxygen
            if resources['oxygen'] is not None:
                excess=max(F(0),resources['oxygen']+oxygen-R['resources']['oxygen']['capacity'])
                overflow+=excess; resources['oxygen']+=oxygen-excess
            ledger('irrigation','consumption','water',pid,F(R['plant']['water']))
            ledger('irrigation','consumption','power',pid,F(R['plant']['power']))
            ledger('irrigation','production','oxygen',pid,oxygen)
    ledger('irrigation','overflow','oxygen','public',overflow)
    stage('irrigation',{'plots':results,'water_used':water_used,'power_used':power_used,'oxygen_produced':oxygen_produced,
                        'oxygen_overflow':None if out['unknown_dependencies'] else overflow},bool(out['unknown_dependencies']))
    crop_notes=[]
    for cid in p.crop_operation_order:
        task=tasks[cid]; plot=plots[task.plot_id]
        known_failure=(task.task=='harvest' and (plot.status=='dead' or results[plot.id]['will_die'] is True))
        crop_notes.append({'crew_id':cid,'task':task.task,'plot_id':plot.id,'status':'known_unavailable' if known_failure else 'requires_world_validation',
                           'reason':'Human does not execute ordered crop operations or credit food.'})
    stage('crop_operations',{'operations':crop_notes,'reason':'outside audited scope'},True)
    out['coverage_end']='after_irrigation_before_crop_operations'
    out['status']='unsafe_in_scope' if any(p['will_die'] is True for p in results.values()) else ('incomplete' if out['unknown_dependencies'] else 'feasible_in_scope')
    out['known_after_values']={'public_resources':resources,'crew':crew}
    return json_numbers(out)
