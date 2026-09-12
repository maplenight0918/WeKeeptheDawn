import copy
import json
import pytest
from fastapi import HTTPException
from app.world_rules import ROOT, F, RULES_HASH
from app.discussion import map_discussion, EXPLANATION_SCHEMA
from app.discussion_types import DiscussionRequest
from app.core_compat import compatible_schema
from app.human_calculator import analyze_baseline
from app.plan_auditor import audit_next_tick
from app.schemas import AnalyzeRequest
from app.unit_conversions import eu_to_kwh, energy_to_eu

@pytest.fixture
def planned():
    return json.loads((ROOT/'examples/discussion_requests/with_plan.json').read_text(encoding='utf-8'))

def mapped(payload):
    return map_discussion(DiscussionRequest.model_validate(payload))

def test_unknown_life_prevents_verified_audit(planned):
    del planned['content']['world']['crew'][0]['alive']
    s,_=mapped(planned); result=analyze_baseline(s)
    assert result['current_world_condition']=='unknown'
    assert result['next_tick_audit']['status']=='incomplete'
    assert result['next_tick_audit']['known_after_values'] is None
    assert not result['next_tick_audit']['ledger']
    assert 'crew.crew-0.alive' in result['missing_fields']
    planned['content']['world']['crew'][0]['water']=0
    s,_=mapped(planned)
    assert analyze_baseline(s)['current_world_condition']=='already_failed'
    assert audit_next_tick(s)['status']=='not_applicable'

@pytest.mark.parametrize('location',['world','content'])
def test_explicit_core_current_plan_maps(planned,location):
    world=planned['content']['world']; plan=world.pop('next_tick_plan')
    target=world if location=='world' else planned['content']
    target['current_plan']={'candidate_plan':plan}
    s,_=mapped(planned)
    assert s.next_tick_plan.model_dump()==plan
    assert audit_next_tick(s)['status']=='feasible_in_scope'
    target['current_plan']['candidate_plan']['for_tick']+=1
    s,context=mapped(planned)
    assert s.next_tick_plan is None and context.payload['adapter_uncertainties']

def test_ambiguous_or_unrecognized_plan_does_not_block_discussion(planned):
    world=planned['content']['world']; world.pop('next_tick_plan')
    world['current_plan']={'task':'some unrecognized format'}
    s,context=mapped(planned)
    assert s.next_tick_plan is None and context.payload['provided_plan']==world['current_plan']
    planned['content']['current_plan']={'task':'a different candidate'}
    s,context=mapped(planned)
    assert s.next_tick_plan is None and len(context.payload['provided_plan'])==2

def test_rule_metadata_and_matching_version_alias_are_compatible(planned):
    rules=planned['content']['rules']; rules['metadata']={'owner':'Core'}
    rules['generation']['description']='Documentation annotation'
    rules['rules_version']=planned['content']['world']['rules_version']='core-v-next-compatible'
    rules['resources']['power']['kwh_per_eu']=3.9745
    s,_=mapped(planned)
    assert audit_next_tick(s)['status']=='feasible_in_scope'
    rules['resources']['power']['kwh_per_eu']=4
    with pytest.raises(HTTPException) as error: mapped(planned)
    assert error.value.status_code==409

def test_changed_execution_description_disables_quantified_verification(planned):
    planned['content']['rules']['tasks']['occupancy']='Crew may perform multiple tasks'
    s,context=mapped(planned)
    assert context.payload['adapter_uncertainties']
    assert audit_next_tick(s)['status']=='incomplete'
    assert 'rules.description_semantics' in audit_next_tick(s)['unknown_dependencies']

def test_schema_annotations_order_and_local_reference_are_compatible():
    altered=copy.deepcopy(EXPLANATION_SCHEMA)
    altered['title']='Core public reply'; altered['required'].reverse()
    proposal=altered['properties'].pop('proposals')
    altered['$defs']={'proposalList':proposal}
    altered['properties']['proposals']={'$ref':'#/$defs/proposalList'}
    assert compatible_schema(altered,EXPLANATION_SCHEMA)
    altered['additionalProperties']=True
    assert not compatible_schema(altered,EXPLANATION_SCHEMA)
    assert not compatible_schema({'$ref':'https://invalid/schema'},EXPLANATION_SCHEMA)
    assert not compatible_schema({'$defs':{'loop':{'$ref':'#/$defs/loop'}},'$ref':'#/$defs/loop'},EXPLANATION_SCHEMA)

def test_energy_conversion_preserves_game_accounting(snapshot):
    assert eu_to_kwh(6000)==23847
    assert energy_to_eu('3.9745')==1
    assert energy_to_eu('3974.5','Wh')==1
    assert energy_to_eu(eu_to_kwh(F('0.448')))==F('0.448')
    result=analyze_baseline(snapshot)
    assert result['public_resource_assessment']['power']['energy_equivalent']['kwh']==23847
    assert result['next_tick_audit']['known_after_values']['public_resources']['power']==6552
    assert RULES_HASH=='8cb7fc2c70beb48f7c3f2edec3819f33f4b4968f899b3e9f3eeed504ae4a2e93'
    for value,unit in [(-1,'kWh'),(1,'kW'),('nan','kWh')]:
        with pytest.raises(ValueError): energy_to_eu(value,unit)

@pytest.mark.parametrize('previous_misses',[1,2])
def test_second_miss_critical_and_third_miss_unsafe(raw,previous_misses):
    raw['plots'][0]['consecutive_unirrigated_ticks']=previous_misses
    raw['next_tick_plan']['irrigation_allocations']=raw['next_tick_plan']['irrigation_allocations'][1:]
    result=analyze_baseline(AnalyzeRequest.model_validate(raw))
    audit=result['next_tick_audit']
    assert audit['status']==('unsafe_in_scope' if previous_misses==2 else 'feasible_in_scope')
    assert audit['fatal_stage'] is None and not audit['fatal_conditions']
    plot=audit['stage_results']['irrigation']['details']['plots'][raw['plots'][0]['id']]
    assert plot['will_die']==(previous_misses==2)
    assert any(r['severity']=='critical' and r['entity_id']==raw['plots'][0]['id'] and r['phase']=='irrigation' for r in result['risks'])
