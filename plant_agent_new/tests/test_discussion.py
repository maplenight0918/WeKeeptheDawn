import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from src.api.discussion_schema import DiscussInput, DiscussOutput
from src.agent.discussion import discuss, rule_summary, energy_summary, policy_notes
from src.retrieval.embedder import ProviderError

class Store:
    def search(self, *args, **kwargs):
        return []

class DiscussionTests(unittest.TestCase):
    def setUp(self):
        self.raw=json.loads(Path('tests/fixtures/discuss_round1.json').read_text(encoding='utf-8'))
        self.raw['content']['rules']['irrigation']['power_per_plot']=energy_summary(1,1)['per_plot_EU_per_tick']
        self.draft={'display_text':'目前有20塊存活作物。建議維持灌溉並由Core分配資源。', 'explanation':{
            'observations':['20塊存活作物'], 'proposals':[{'proposal_id':'new-p1','strategy':'維持灌溉','reason':'避免死亡','expected_effect':'供應成功才生長','tradeoffs':['消耗水電'],'evidence':['rules.irrigation']}],
            'reviews':[], 'conflicts':[], 'follow_up_reason':'', 'decision_reason':'保留生長進度', 'uncertainties':['Core部署位址尚未提供']}}

    def test_round1_contract_and_arithmetic(self):
        inp=DiscussInput.model_validate(self.raw)
        summary=rule_summary(inp)
        self.assertEqual(summary['full_irrigation_water_L_per_tick'],174)
        self.assertAlmostEqual(summary['full_irrigation_power_EU_per_tick_under_received_rules'],4.166780617742457)
        self.assertEqual(summary['oxygen_OU_if_all_living_plots_irrigated'],304)
        self.assertEqual(summary['living_area_m2'],100)
        with patch('src.agent.discussion.complete',return_value=self.draft):
            out=discuss(Store(),inp)
        self.assertNotEqual(out.message_id,inp.message_id)
        self.assertEqual((out.discussion_id,out.round,out.world_version),(inp.discussion_id,1,0))
        self.assertEqual(len(out.content.model_dump()),5)
        self.assertEqual(out.content.suggested_actions[0]['description'],out.explanation.proposals[0].strategy)
        self.assertNotIn('data',out.model_dump())

    def test_round2_history_and_invalid_reference(self):
        old={'message_id':'human-old','discussion_id':self.raw['discussion_id'],'world_version':0,'round':1,
             'explanation':{'proposals':[{'proposal_id':'human-p1'}]}}
        self.raw['round']=2
        self.raw['content']['previous_messages']=[old]
        self.raw['explanation']['follow_up_reason']='需要協調用電'
        self.draft['explanation']['reviews']=[{'message_id':'human-old','proposal_id':'human-p1','disposition':'modify','assessment':'需保留灌溉需求'}]
        with patch('src.agent.discussion.complete',return_value=self.draft) as call:
            out=discuss(Store(),DiscussInput.model_validate(self.raw))
            self.assertIn('需要協調用電',call.call_args.args[1])
        self.assertEqual(out.round,2)
        self.draft['explanation']['reviews'][0]['proposal_id']='invented'
        with patch('src.agent.discussion.complete',return_value=self.draft), self.assertRaises(ProviderError):
            discuss(Store(),DiscussInput.model_validate(self.raw))

    def test_bad_input_and_output(self):
        for modify in [lambda r:r.update(world_version=1),lambda r:r['content']['world']['resources'].update(EU=10),
                       lambda r:r['content']['world']['plots'].pop(),lambda r:r['content']['world']['crew'][1].update(id='crew-0')]:
            r=copy.deepcopy(self.raw);modify(r)
            with self.assertRaises(ValidationError):DiscussInput.model_validate(r)
        self.raw['content']['world']['extra_backend_info']={'paused':True}
        DiscussInput.model_validate(self.raw)
        self.draft['explanation']['unexpected']='no'
        with patch('src.agent.discussion.complete',return_value=self.draft), self.assertRaises(ProviderError):
            discuss(Store(),DiscussInput.model_validate(self.raw))

    def test_energy_uses_unrounded_model_and_hourly_ticks(self):
        one=energy_summary(1,1)
        self.assertAlmostEqual(one['per_plot_power_kW'],0.8280434782608697)
        self.assertAlmostEqual(one['total_EU_per_tick'],0.20833903088712283)
        self.assertAlmostEqual(energy_summary(4,1)['total_kWh_per_day'],79.49217391304349)
        self.assertAlmostEqual(energy_summary(20,1)['total_EU_per_tick'],4.166780617742457)
        self.assertAlmostEqual(one['total_EU_per_day']/24,one['total_EU_per_tick'])
        self.assertAlmostEqual(energy_summary(20,2)['total_EU_per_tick'],2*energy_summary(20,1)['total_EU_per_tick'])

    def test_old_and_synchronized_rules_and_no_world_mutation(self):
        self.raw['content']['rules']['irrigation']['power_per_plot']=5
        inp=DiscussInput.model_validate(self.raw)
        before=inp.model_dump()
        with patch('src.agent.discussion.complete',return_value=self.draft) as model:
            out=discuss(Store(),inp)
            model.assert_called_once()
        self.assertEqual(inp.model_dump(),before)
        self.assertTrue(any('100.000000 EU' in x and '4.166781 EU' in x for x in out.explanation.conflicts))
        self.assertTrue(any('4.166781 EU' in x for x in out.content.evidence_and_unknowns))
        self.raw['content']['rules']['irrigation']['power_per_plot']=energy_summary(1,1)['per_plot_EU_per_tick']
        summary=rule_summary(DiscussInput.model_validate(self.raw))
        self.assertTrue(summary['received_power_matches_plant'])
        self.assertEqual(policy_notes(summary)[1],[])

    def test_core_rejection_continues_under_received_rules(self):
        self.raw['content']['rules']['irrigation']['power_per_plot']=5
        self.raw['round']=2
        old={'message_id':'plant-old','sender':'plant','discussion_id':self.raw['discussion_id'],
             'world_version':0,'round':1,'explanation':{'proposals':[{'proposal_id':'plant-energy-old','strategy':'請修改耗電規則'}]}}
        self.raw['content']['previous_messages']=[old]
        self.raw['explanation']['reviews']=[{'message_id':'plant-old','proposal_id':'plant-energy-old',
            'disposition':'reject','assessment':'不更改世界規則，請依100 EU/tick討論。'}]
        self.draft['explanation']['reviews']=[{'message_id':'plant-old','proposal_id':'plant-energy-old',
            'disposition':'modify','assessment':'接受Core限制，依現行規則維持灌溉。'}]
        inp=DiscussInput.model_validate(self.raw)
        before=inp.model_dump()
        with patch('src.agent.discussion.complete',return_value=self.draft) as model:
            out=discuss(Store(),inp)
        payload=json.loads(model.call_args.args[1])
        self.assertEqual(payload['request']['explanation']['reviews'][0]['disposition'],'reject')
        summary=payload['calculated_rule_summary']
        self.assertEqual(summary['full_irrigation_power_EU_per_tick_under_received_rules'],100)
        self.assertEqual(summary['water_production_for_plant_only']['plant_power_plus_replacement_water_power_EU_per_tick'],448)
        self.assertAlmostEqual(summary['plant_energy']['total_EU_per_tick'],4.166780617742457)
        self.assertEqual(out.explanation.reviews[0].proposal_id,'plant-energy-old')
        self.assertEqual(out.explanation.proposals[0].strategy,'維持灌溉')
        self.assertEqual(inp.model_dump(),before)

    def test_only_living_area_counts(self):
        plots=self.raw['content']['world']['plots']
        for p in plots:
            p.update(status='empty',crop_type=None,growth_ticks=0)
        summary=rule_summary(DiscussInput.model_validate(self.raw))
        self.assertEqual(summary['plant_energy']['total_EU_per_tick'],0)
        plots[0].update(status='dead',crop_type='lettuce')
        plots[1].update(status='mature',crop_type='lettuce',growth_ticks=30)
        summary=rule_summary(DiscussInput.model_validate(self.raw))
        self.assertEqual(summary['living_area_m2'],5)
        self.assertAlmostEqual(summary['plant_energy']['total_EU_per_tick'],0.20833903088712283)

    def test_tick_disagreement_is_explicit(self):
        self.raw['content']['rules']['tick_hours']=2
        summary=rule_summary(DiscussInput.model_validate(self.raw))
        self.assertFalse(summary['tick_matches_agreed_hour'])
        self.assertTrue(any('1小時' in x for x in policy_notes(summary)[1]))

    def test_water_production_capacity_comparison(self):
        c=rule_summary(DiscussInput.model_validate(self.raw))['water_production_for_plant_only']
        self.assertEqual(c['plant_irrigation_L_per_tick'],174)
        self.assertEqual(c['production_limit_L_per_tick'],250)
        self.assertTrue(c['plant_irrigation_within_production_limit'])
        self.assertEqual(c['production_spare_capacity_L_per_tick'],76)
        self.assertEqual(c['power_EU_to_replace_plant_irrigation_water'],348)
        self.assertAlmostEqual(c['plant_power_plus_replacement_water_power_EU_per_tick'],352.16678061774246)
