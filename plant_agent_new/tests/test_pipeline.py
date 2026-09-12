"""Offline regression tests: formulas, contracts, retrieval, and agent fallback."""
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from pydantic import ValidationError

from src.agent.llm import parse_json
from src.agent.plant_agent import TUNABLE, analyze
from src.agent.prompts import NARRATE_SYSTEM, SELECT_SYSTEM
from src.api.schema import PlantAgentInput, PlantAgentOutput
from src.models.coefficients import Coefficients
from src.models.greenhouse import simulate, sweep_ppfd
from src.retrieval.store import CorpusStore, Hit


class ModelTests(unittest.TestCase):
    def test_five_crops_and_daily_contract(self):
        for crop, edible, oxygen in [('lettuce',390,.023), ('potato',325,.093),
                                     ('tomato',260,.028), ('wheat',195,.408), ('soybean',139,.334)]:
            with self.subTest(crop=crop):
                out = simulate(Coefficients(crop), PlantAgentInput(crop=crop))
                self.assertEqual(round(out['supply']['edible_g_day']), edible)
                self.assertEqual(round(out['supply']['o2_kg_day'], 3), oxygen)
                self.assertEqual(set(out['daily_rate']), {'o2_kg_per_day','edible_g_per_day',
                                  'water_l_per_day','power_kwh_per_day','co2_kg_per_day'})
                self.assertAlmostEqual(out['supply']['water_recycled_l_day'], out['demand']['water_l_day'] * .92)
                self.assertEqual(out['daily_rate']['power_kwh_per_day'], round(out['demand']['power_kw'] * 24, 2))

    def test_budget_and_sweep(self):
        inp = PlantAgentInput(crop='wheat', area=40, ppfd=400, photoperiod=16,
                              temperature=24, co2=1000, power_budget=8)
        coeffs = Coefficients('wheat')
        out = simulate(coeffs, inp)
        self.assertEqual(out['intermediate']['effective_ppfd'], 304.6)
        self.assertAlmostEqual(out['demand']['power_kw'], 8)
        self.assertIn('10.41 kW', out['warnings'][0])
        rows = sweep_ppfd(coeffs, inp, [240,320,400,480,600])
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]['ppfd'], 400)
        self.assertIsNone(rows[0]['power_delta_pct'])
        self.assertEqual((rows[1]['power_delta_pct'], rows[1]['edible_delta_pct']), (-38.8,-15.8))
        self.assertEqual(inp.power_budget, 8)

    def test_monotonicity_and_environment(self):
        for crop in ['lettuce','potato','tomato','wheat','soybean']:
            coeffs = Coefficients(crop)
            values = [simulate(coeffs, PlantAgentInput(crop=crop,ppfd=x))['supply']['edible_g_day']
                      for x in [0,100,150,200,250,400,1000,2000]]
            self.assertEqual(values, sorted(values))
        base = simulate(Coefficients('lettuce'), PlantAgentInput())
        for change in [{'humidity':20}, {'density':5}, {'temperature':0}]:
            out = simulate(Coefficients('lettuce'), PlantAgentInput(**change))
            self.assertLess(out['supply']['edible_g_day'], base['supply']['edible_g_day'])
        dense = simulate(Coefficients('lettuce'), PlantAgentInput(density=100))
        self.assertEqual(dense['health'], base['health'])
        self.assertEqual(base['health'], 1)

    def test_darkness_minimum_power_and_validation(self):
        for change in [{'ppfd':0}, {'photoperiod':0}]:
            out = simulate(Coefficients('lettuce'), PlantAgentInput(**change))
            self.assertEqual(out['supply']['edible_g_day'], 0)
            self.assertEqual(out['supply']['o2_kg_day'], 0)
        out = simulate(Coefficients('lettuce'), PlantAgentInput(power_budget=0))
        self.assertEqual(out['intermediate']['effective_ppfd'], 0)
        self.assertAlmostEqual(out['demand']['power_kw'], .16)
        self.assertTrue(any('最低需求' in x for x in out['warnings']))
        for change in [{'area':0}, {'ppfd':2001}, {'co2':float('nan')}, {'power_budget':-1}]:
            with self.assertRaises(ValidationError):
                PlantAgentInput(**change)


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = CorpusStore()

    def test_real_index_alignment(self):
        self.assertEqual(len(self.store.chunks), 64160)
        self.assertEqual(self.store.vecs.shape, (64160,1024))
        np.testing.assert_allclose(np.linalg.norm(self.store.vecs[::1000], axis=1), 1, atol=1e-5)

    def test_filter_order_scores_and_doc_cap(self):
        with patch('src.retrieval.store.embed', return_value=self.store.vecs[0]):
            hits = self.store.search('local vector test', crops=['lettuce'], units=['harvest_weight'], fallback=False)
        self.assertTrue(hits)
        self.assertTrue(all('lettuce' in h.crops and 'harvest_weight' in h.units for h in hits))
        self.assertEqual([h.score for h in hits], sorted([h.score for h in hits], reverse=True))
        self.assertTrue(all(sum(x.doc_id == h.doc_id and x.source == h.source for x in hits) <= 2 for h in hits))

    def test_fallback_and_queries(self):
        with patch('src.retrieval.store.embed', return_value=self.store.vecs[0]) as embed:
            self.assertEqual(self.store.search('x', tiers=['absent']), [])
            embed.assert_not_called()
            self.assertTrue(self.store.search('x', crops=['absent'], units=['absent']))
        with patch.object(self.store, 'search', return_value=[]) as search:
            self.store.coefficient_evidence('biomass_rate', 'lettuce')
            self.assertEqual(search.call_args.args[0], 'lettuce: edible biomass productivity per unit area per day, dry weight yield in controlled environment')
            for key in TUNABLE:
                self.store.coefficient_evidence(key, 'lettuce')
                self.assertTrue(search.call_args.kwargs['units'])


class AgentTests(unittest.TestCase):
    def test_prompts_exact_and_json_wrappers(self):
        spec = Path('docs/SPEC.md').read_text(encoding='utf-8')
        for heading, actual in [('### 步驟 1 的 system prompt（逐字）', SELECT_SYSTEM),
                                ('### 步驟 3 的 system prompt（逐字）', NARRATE_SYSTEM)]:
            expected = re.search(r'```\n(.*?)\n```', spec.split(heading,1)[1], re.S).group(1)
            self.assertEqual(actual, expected)
        self.assertEqual(parse_json('說明 ```json\n{"a": 1}\n``` 完成'), {'a':1})

    def test_rejected_values_and_evidence_fallback(self):
        class Store:
            def coefficient_evidence(self, key, crop, k):
                return [Hit('PMC:D:1', .8, 'Example 0.35', 'D', 'PMC', 'Test evidence', '',
                            'A_plant_core', '', ['lettuce'], ['water_use'])]
        for value in [.35, 1000]:
            replies = [{'transpiration': {'value':value,'source':'PMC:D','note':''}},
                       {'reasoning':'測試敘事','tradeoff':'省 20% 電力','risks':[]}]
            with patch('src.agent.plant_agent.complete', side_effect=replies):
                out = analyze(Store(), PlantAgentInput())
            PlantAgentOutput.model_validate(out)
            self.assertEqual(out['coefficients']['transpiration']['value'], 5)
            self.assertEqual(out['citations'], [])
            self.assertTrue(out['evidence'])
            self.assertTrue(any('退回中位數' in x for x in out['warnings']))

    def test_adopted_citation(self):
        class Store:
            def coefficient_evidence(self, key, crop, k):
                return [Hit('PMC:D:1', .8, 'biomass 30', 'D', 'PMC', 'Test evidence', '',
                            'A_plant_core', '', ['lettuce'], ['yield_value'])]
        with patch('src.agent.plant_agent.complete', side_effect=[
            {'biomass_rate':{'value':30,'source':'PMC:D','note':'mocked evidence'}},
            {'reasoning':'測試','tradeoff':'省 20% 電力','risks':[]}]):
            out = analyze(Store(), PlantAgentInput())
        self.assertEqual(out['citations'], ['PMC:D'])
        self.assertEqual(out['coefficients']['biomass_rate']['value'], 30)


if __name__ == '__main__':
    unittest.main()
