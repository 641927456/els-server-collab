import copy
import json
import tempfile
import unittest
from pathlib import Path
from els_server.paths import PROJECT_ROOT
from els_server.game_data import DATA_DIR
from els_server.manufacture_data import ManufactureData, COUNTS
from tools.build_manufacture_catalog import build, transform

SOURCE = PROJECT_ROOT/'analysis/integration-20261015/manufacture-resources'


class ManufactureDataTests(unittest.TestCase):
    def test_native_materials_cost_and_profession_restrictions_preserved(self):
        c = ManufactureData()
        self.assertEqual(c.manifest['counts'], COUNTS)
        self.assertEqual(len(c.ids()), 12360)
        r = c.recipe(30445)
        self.assertEqual(r['definition']['m_Cost'], 268800)
        self.assertEqual(r['definition']['m_MaterialTable'], {
            '1': {'m_MaterialCount':1, 'm_MaterialID':154059},
            '2': {'m_MaterialCount':600, 'm_MaterialID':154053}})
        p = c.recipe(10078906)['definition']
        self.assertEqual((p['m_RequireProfessionType'], p['m_LimitProfessionLevel'], p['m_Cost']), (3,8,22600))
        self.assertFalse(r['transaction_implemented'])
        self.assertEqual(c.period_rules()['limits'], [{'LimitCountInPeriod':30,'LimitManufactureID':10130467,'LimitUnitType':1,'LimitPeriodType':2}])

    def test_source_registrations_and_result_order_are_not_lost(self):
        c = ManufactureData()
        calls = json.loads((SOURCE/'ManufactureItem.lua.tables.json').read_text(encoding='utf8'))['__symbolic_calls__']
        recipes, groups, villages = {}, {}, {}
        for call in calls:
            args = call['arguments'][1:]
            if call['function'].endswith('AddManufactureTemplet'): recipes[args[0]['m_ManufactureID']] = args[0]
            elif call['function'].endswith('AddManufactureResultGroup'): groups.setdefault(args[0], []).append(args[1])
            else: villages.setdefault(args[0], []).append(args)
        for identity, original in recipes.items():
            row = c.recipe(identity)
            self.assertEqual(row['definition'], original)
            self.assertEqual(row['result_registrations'], groups.get(original['m_ResultGroupID'], []))
            self.assertEqual(row['village_registrations'], villages.get(identity, []))
        self.assertEqual(sum(not c.recipe(i)['result_registrations'] for i in c.ids()), 2)

    def test_immutable_lookup_reproducible_build_and_corruption_rejection(self):
        c = ManufactureData()
        r = c.recipe(30445); r['definition']['m_Cost'] = -1; r['result_registrations'].clear()
        self.assertEqual(c.recipe(30445)['definition']['m_Cost'], 268800)
        for identity in (True, 30445.0, 0, -1):
            with self.assertRaises(ValueError): c.recipe(identity)
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            build(SOURCE, folder)
            self.assertEqual((folder/'manufacture.json').read_bytes(), (DATA_DIR/'manufacture.json').read_bytes())
            with (folder/'manufacture.json').open('ab') as f: f.write(b' ')
            with self.assertRaises(ValueError): ManufactureData(folder)
