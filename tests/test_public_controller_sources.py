"""Portable public-controller source contracts; no native asset claim."""
from pathlib import Path
import ast
from types import SimpleNamespace
import unittest

from els_server.domain.public_controller_rules import RULES

ROOT=Path(__file__).resolve().parents[1]
MASTERS=(*range(34370,34501,10),34690,34700)
PUBLIC={*MASTERS,34060,34090,34170,34180,34190}

class PublicControllerSourceTests(unittest.TestCase):
    def test_public_sources_keep_all_character_and_native_identity_bounds(self):
        self.assertEqual(len(RULES),135)
        self.assertEqual({r['dungeon']for r in RULES},PUBLIC)
        seen=set()
        for row in RULES:
            key=tuple(row[k]for k in ('dungeon','stage','part','template'))+(row['source']['source_index'],)
            self.assertNotIn(key,seen);seen.add(key)
            self.assertTrue(row['quest_independent'])
            self.assertTrue(row['requires_native_255'])
            self.assertEqual(row['units'],list(range(1,16)))
            self.assertEqual(row['template'],row['source']['template'])
            self.assertRegex(row['graph_sha'],r'^[0-9a-f]{64}$')
            self.assertRegex(row['script_sha'],r'^[0-9a-f]{64}$')
            self.assertTrue(row['script'].lower().endswith('.lua'))

    def test_master_road_clear_markers_have_public_receivers(self):
        # Original kind-3 clear targets, including both normal and hell modes.
        targets=(7623,7633,7803,7810,7645,7655,7824,7844,7667,7680,7859,7869,7703,7737,8124,8134)
        for dungeon,template in zip(MASTERS,targets):
            row=next(r for r in RULES if r['dungeon']==dungeon and r['template']==template)
            self.assertTrue(row['gate'])
            self.assertEqual((row['stage'],row['part']),(0,0))

    def test_real_source_selector_preserves_character_specific_story_rules(self):
        path=ROOT/'els_server/domain/story_controller_retirements.py'
        tree=ast.parse(path.read_text(encoding='utf8'))
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign)
                        and any(isinstance(t,ast.Name)and t.id=='RULES'for t in n.targets))
        story=ast.literal_eval(assignment.value)
        selector=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='rules_for')
        namespace={'RULES':story}
        # Execute the actual selector with its actual source rows. Other
        # runtime functions are deliberately outside this portable check.
        exec(compile(ast.Module(body=[selector],type_ignores=[]),str(path),'exec'),namespace)
        select=namespace['rules_for']
        for dungeon in {r['dungeon']for r in story}-PUBLIC:
            self.assertEqual(select(SimpleNamespace(identity=dungeon)),tuple(r for r in story if r['dungeon']==dungeon))
        for dungeon in PUBLIC:
            selected=select(SimpleNamespace(identity=dungeon))
            public=[r for r in selected if r.get('quest_independent')]
            self.assertCountEqual(public,[r for r in RULES if r['dungeon']==dungeon])

if __name__=='__main__':unittest.main()
