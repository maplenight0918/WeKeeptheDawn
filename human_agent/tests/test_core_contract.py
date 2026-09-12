import copy
import httpx
import pytest
from examples.brain_client import map_core_snapshot, validate_response_identity, response_is_current, analyze
from app.schemas import AnalyzeRequest

def test_core_mapping_preserves_snapshot_without_unit_guessing(raw):
    core={'request_id':raw['request_id'],'snapshot_id':raw['state_id'],'tick':raw['tick'],'status':raw['world_status'],
          'public_resources':raw['resources'],'people':raw['crew'],'plots':raw['plots'],
          'water_device_available':raw['water_production_available'],'proposed_next_tick':raw['next_tick_plan']}
    before=copy.deepcopy(core)
    mapped=map_core_snapshot(core)
    assert AnalyzeRequest.model_validate(mapped).model_dump()==AnalyzeRequest.model_validate(raw).model_dump()
    assert core==before

@pytest.mark.parametrize('key',['schema_version','world_rules_version','request_id','state_id','tick','for_tick'])
def test_core_rejects_identity_mismatch(raw,key):
    response={k:raw[k] for k in ['schema_version','world_rules_version','request_id','state_id','tick']}
    response['for_tick']=1
    validate_response_identity(response,raw)
    response[key]='wrong'
    with pytest.raises(ValueError): validate_response_identity(response,raw)

def test_core_rechecks_latest_state_before_adoption():
    response={'state_id':'old','tick':3,'for_tick':4}
    assert response_is_current(response,'old',3)
    assert not response_is_current(response,'new',3)
    assert not response_is_current(response,'old',4)

def test_http_client_preserves_critical_and_degraded(raw):
    def handler(request):
        return httpx.Response(200,json={**{k:raw[k] for k in ['schema_version','world_rules_version','request_id','state_id','tick']},'for_tick':1,'execution_mode':'degraded','risks':[{'severity':'critical'}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=analyze(client,'http://core-test',raw)
        assert result['execution_mode']=='degraded' and result['risks'][0]['severity']=='critical'
