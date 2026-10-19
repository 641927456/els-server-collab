import copy
import json
import tempfile
import unittest
from pathlib import Path
from els_server.paths import PROJECT_ROOT
from els_server.game_data import DATA_DIR
from els_server.profession_data import ProfessionData, REGISTRATION_COUNTS, validate_registrations
from tools.build_profession_catalog import build


class ProfessionDataTests(unittest.TestCase):
    def test_all_native_callbacks_preserved_and_current_definitions_accessible(self):
        data = ProfessionData()
        original = json.loads((PROJECT_ROOT/'analysis/integration-20261015/profession-resources/ProfessionTemplet.lua.tables.json').read_text(encoding='utf8'))
        expected = {}
        for call in original['__symbolic_calls__']:
            expected.setdefault(call['function'].split('.')[-1], []).append(call['arguments'][1:])
        self.assertEqual(sum(map(len, expected.values())), 88)
        for name in REGISTRATION_COUNTS:
            self.assertEqual(data.registrations(name), expected[name])
        self.assertEqual([data.template(i)['m_eType'] for i in (1, 2, 3)], [1, 2, 3])
        self.assertEqual(data.registrations('AddMaxBlackSmithHammerByLevel'), [[i, 2*i] for i in range(1, 11)])
        self.assertEqual(data.registrations('SetProfessionFreeChangeMaxCount'), [[3]])
        self.assertEqual(data.registrations('SetResetAnvilPeriod'), [[8]])

    def test_callers_cannot_mutate_catalog_or_alias_invalid_identity(self):
        data = ProfessionData()
        before = data.template(1)
        result = data.template(1)
        result['m_wstrTitleList'].clear()
        self.assertEqual(data.template(1), before)
        settings = data.settings()
        settings['AddMaxBlackSmithHammerByLevel'][0][1] = 999
        self.assertEqual(data.registrations('AddMaxBlackSmithHammerByLevel')[0], [1, 2])
        manifest = data.manifest
        manifest['limits'].clear()
        self.assertTrue(data.manifest['limits'])
        for identity in (True, 1.0, '1', 0, 4):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                data.template(identity)
        with self.assertRaises(ValueError):
            data.registrations('MissingMethod')

    def test_rebuild_identity_and_fail_closed_for_mutated_content(self):
        source = PROJECT_ROOT/'analysis/integration-20261015/profession-resources'
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            build(source, dest)
            self.assertEqual((dest/'professions.json').read_bytes(), (DATA_DIR/'professions.json').read_bytes())
            ProfessionData(dest)
            raw = json.loads((dest/'professions.json').read_text(encoding='utf8'))
            raw['__symbolic_calls__'][3]['arguments'][-1] = 999
            (dest/'professions.json').write_text(json.dumps(raw), encoding='utf8')
            with self.assertRaises(ValueError):
                ProfessionData(dest)
        calls = json.loads((source/'ProfessionTemplet.lua.tables.json').read_text(encoding='utf8'))['__symbolic_calls__']
        for mutation in ('missing', 'owner', 'method', 'duplicate_type'):
            altered = copy.deepcopy(calls)
            if mutation == 'missing':altered.pop()
            elif mutation == 'owner':altered[0]['arguments'][0] = {'global': 'other'}
            elif mutation == 'method':altered[0]['function'] = 'g_pProfessionManager.Unknown'
            else:altered[0]['arguments'][1]['m_eType'] = 2
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_registrations(altered)
