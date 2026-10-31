"""Appearance boundaries must not change the amount retained by the caller."""
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
# The accepted historical engine remains pinned; exercise this candidate in
# this standalone test process without changing its selected profile.
import els_server.domain
els_server.domain.__path__.insert(0,str(Path(__file__).resolve().parents[1]/
    'references/ground-drop-models-20261101-v1/source/els_server/domain'))
from els_server.domain.ground_currency import coin_template
from els_server.domain.hunter_chest_rules import source_route,SOURCE_ROUTES


class GroundCurrencyTests(unittest.TestCase):
    def test_display_boundaries(self):
        for amount,template in ((1,127000),(50,127000),(51,127010),(150,127010),
                                (151,127020),(1999,127020),(2000,127041),(2**31-1,127041)):
            with self.subTest(amount=amount):
                self.assertEqual(coin_template(amount),template)

    def test_invalid_amounts(self):
        for value in (0,-1,True,1.0,2**31,None):
            with self.subTest(value=value),self.assertRaises(ValueError):coin_template(value)

    def test_reward_source_uses_amount_instead_of_fixed_copper(self):
        from els_server.domain import reward_rules
        policy={'dungeons':{'30000':{'ground_loot':{
            'assignment_source':'local_fallback','native_probabilities_known':False,
            'npc_loot':{'618':{'coin':{'template':127000,'amount':151}}}}}}}
        npc={'template':618,'active':True,'no_drop':False,'key':0}
        with patch.object(reward_rules,'_policy',return_value=policy),\
             patch.object(reward_rules,'dungeon_rewards',return_value={}),\
             patch('els_server.domain.gm_rates.allow_drop',return_value=True),\
             patch('els_server.domain.formal_pve_economy.coin',side_effect=lambda identity,boss,fallback:fallback):
            self.assertEqual(reward_rules.ground_loot(30000,npc,'source-run',0,6),
                             [{'template':127020,'ed':151,'quantity':0}])


class HunterOrdinarySourceTests(unittest.TestCase):
    def run_fixture(self,identity=30092,digest='native-graph',encounter=None):
        return NS(identity=identity,graph=dict(source_sha256=digest,encounter=encounter),
                  catalog=NS(_data={'routes':{str(identity):{}}}))

    def test_ordinary_source_requires_current_graph(self):
        row={'graph_sha256':'native-graph'}
        with patch('els_server.domain.formal_pve_economy.definition',return_value=row),\
             patch('els_server.game_data.client_data')as data:
            data.return_value.dungeon.return_value={'m_MaxLevel':7}
            self.assertEqual(source_route(self.run_fixture()),(7,'native-graph'))
            with self.assertRaises(ValueError):source_route(self.run_fixture(digest='changed'))
            with self.assertRaises(ValueError):source_route(self.run_fixture(encounter={'kind':'special'}))
            run=self.run_fixture();run.catalog._data['routes']={}
            with self.assertRaises(ValueError):source_route(run)

    def test_special_and_archived_sources_stay_excluded(self):
        with patch('els_server.domain.formal_pve_economy.definition',return_value=None):
            with self.assertRaises(ValueError):source_route(self.run_fixture(33031))
        with patch('els_server.domain.formal_pve_economy.definition',return_value={'graph_sha256':'native-graph'}):
            with self.assertRaises(ValueError):source_route(self.run_fixture(41400))

    def test_original_five_sources_keep_their_pins(self):
        for identity,(level,digest) in SOURCE_ROUTES.items():
            self.assertEqual(source_route(self.run_fixture(identity,digest)),(level,digest))
            with self.assertRaises(ValueError):source_route(self.run_fixture(identity,'changed'))


if __name__=='__main__':unittest.main()
