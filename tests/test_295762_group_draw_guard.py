"""Finite internal draw regression; native group admission stays refused."""
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import types
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'references/native-aurora-book-sources-20261027-v1/shared/els_server'


class SoloBookDrawGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        policy = json.loads((ART / 'data/formal_pve_economy.json').read_bytes())
        source = ART / 'domain/formal_pve_economy.py'
        function = next(n for n in ast.parse(source.read_text()).body
                        if isinstance(n, ast.FunctionDef) and n.name == 'clear_items')
        scope = dict(definition=lambda identity: policy['maps'].get(str(identity)),
                     policy=lambda: policy, uuid=uuid, hashlib=hashlib, struct=struct)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
        cls.draw = staticmethod(scope['clear_items'])

    def setUp(self):
        reward = types.ModuleType('els_server.domain.reward_rules')
        reward.item_plan = lambda template, quantity: dict(template=template, quantity=quantity)
        data = types.ModuleType('els_server.game_data')
        data.client_data = lambda: types.SimpleNamespace(unit=lambda _: {'unitType': 1})
        self.modules = patch.dict(sys.modules, {reward.__name__: reward, data.__name__: data})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_known_book_draws_stay_solo_and_group_retains_original_material(self):
        for identity, seed in ((140010, 10), (140020, 12), (140030, 37)):
            with self.subTest(identity=identity):
                args = (identity, str(uuid.UUID(int=seed)), 1001, {'unit_class': 1})
                self.assertEqual(self.draw(*args), [{'template': 295762, 'quantity': 1}])
                self.assertEqual(self.draw(*args, group=True), [{'template': 30600, 'quantity': 1}])

    def test_draw_hits_and_existing_material_plans_are_not_changed(self):
        for identity in (140010, 140020, 140030):
            hits = books = materials = 0
            for seed in range(1, 1001):
                args = (identity, str(uuid.UUID(int=seed)), 1001, {'unit_class': 1})
                solo = self.draw(*args)
                group = self.draw(*args, group=True)
                self.assertEqual(bool(solo), bool(group))
                if solo:
                    hits += 1
                    if solo[0]['template'] == 30600:
                        materials += 1
                        self.assertEqual(solo, group)
                    else:
                        books += 1
                    self.assertEqual(group, [{'template': 30600, 'quantity': 1}])
            self.assertGreater(hits, 0)
            self.assertGreater(books, 0)
            self.assertGreater(materials, 0)


if __name__ == '__main__':
    unittest.main()
