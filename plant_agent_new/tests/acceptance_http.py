"""Real HTTP acceptance checks; missing credentials are reported as blocked."""
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8000'
results = {}


def call(path, body=None):
    start = time.monotonic()
    request = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type':'application/json'})
    try:
        with urlopen(request, timeout=90) as response:
            return response.status, json.load(response), time.monotonic() - start
    except HTTPError as exc:
        return exc.code, json.load(exc), time.monotonic() - start


status, body, seconds = call('/health')
assert status == 200 and body['chunks'] == 64160
results['health'] = body
results['simulate'] = []
for crop, edible, oxygen in [('lettuce',390,.023),('potato',325,.093),('tomato',260,.028),('wheat',195,.408),('soybean',139,.334)]:
    status, body, seconds = call('/simulate', {'crop':crop})
    assert status == 200
    assert round(body['supply']['edible_g_day']) == edible
    assert round(body['supply']['o2_kg_day'],3) == oxygen
    results['simulate'].append({'crop':crop, **body['supply']})
status, body, seconds = call('/world/crops')
assert status == 200
assert [round(x['edible_g_m2_day'],2) for x in body['crops']] == [19.5,16.25,13,9.75,6.93]
results['world_crops'] = [{k:v for k,v in row.items() if k != 'coefficients'} for row in body['crops']]
scenario = dict(crop='wheat',area=40,ppfd=400,photoperiod=16,temperature=24,co2=1000,power_budget=8)
status, body, seconds = call('/simulate',scenario)
assert status == 200 and body['intermediate']['effective_ppfd'] == 304.6
results['budget'] = {'warnings':body['warnings'],'intermediate':body['intermediate']}
status, body, seconds = call('/sweep',scenario)
assert status == 200
row = next(x for x in body if x['ppfd'] == 240)
assert (row['power_delta_pct'],row['edible_delta_pct']) == (-38.8,-15.8)
results['sweep_240'] = row
query = urlencode(dict(q='lettuce: edible biomass productivity per unit area per day, dry weight yield in controlled environment',
                       crop='lettuce',units='biomass_rate,yield_value,harvest_weight'))
status, body, seconds = call('/search?' + query)
results['search'] = {'status':status,'seconds':seconds,'body':body}
results['search']['passed'] = (status == 200 and len(body) >= 3
    and all(abs(hit['score']-expected)<.002 for hit,expected in zip(body[:3],[.810,.805,.800]))
    and body[0]['title'].startswith('Soilless Cultivation'))
print('SEARCH:', json.dumps(results['search'],ensure_ascii=False), flush=True)
status, body, seconds = call('/analyze', {'crop':'lettuce'})
results['analyze'] = {'status':status,'seconds':seconds,'body':body}
results['analyze']['passed'] = bool(status == 200 and seconds < 40 and body['citations'] and body['evidence'] and '%' in body['tradeoff'])
Path('docs/acceptance_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
