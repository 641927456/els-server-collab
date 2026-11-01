"""Regression contract between native public gates and their retirement policy."""
import unittest
from els_server.domain.dungeon_routes import route_catalog
from els_server.domain.region_quests import region_catalog
from els_server.domain.public_controller_rules import RULES
from els_server.domain.story_controller_retirements import rules_for,RULES as STORY_RULES

class PublicControllerRulesTests(unittest.TestCase):
 def test_public_gate_sources_do_not_depend_on_optional_story_tasks(self):
  routes=route_catalog();regions=region_catalog();seen=set()
  for rule in RULES:
   identity=tuple(rule[k]for k in ('dungeon','stage','part','template'))+(rule['source']['source_index'],)
   self.assertNotIn(identity,seen);seen.add(identity)
   self.assertTrue(rule['quest_independent'])
   self.assertEqual(rule['units'],list(range(1,16)))
   graph=routes.graph(rule['dungeon'])
   self.assertEqual(graph['source_sha256'],rule['graph_sha'])
   room=graph['stages'][str(rule['stage'])]['parts'][str(rule['part'])]
   self.assertIn(rule['source'],[n for group in room['groups']for n in group['npcs']])
   self.assertEqual(routes.manifest['source_sha256'][rule['script']],rule['script_sha'])
   prerequisite={regions.data['regions'].get(str(r),{}).get('requirement',{}).get('RequireQuestID')
                for r in regions.data['dungeons'][str(rule['dungeon'])]}-{None,0}
   self.assertTrue(all(regions.dungeon_allowed(rule['dungeon'],dict(level=99,unit_type=u),prerequisite)for u in range(1,16)))

 def test_every_master_road_native_clear_marker_has_a_public_receiver(self):
  for dungeon in (*range(34370,34501,10),34690,34700):
   graph=route_catalog().graph(dungeon)
   for stage,scene in graph['stages'].items():
    for part,room in scene['parts'].items():
     for condition in room['conditions']:
      if condition['kind']!=3:continue
      for template in condition['required']:
       self.assertTrue(any((r['dungeon'],r['stage'],r['part'],r['template'])==(dungeon,int(stage),int(part),template)for r in RULES))

 def test_character_specific_story_rules_keep_their_original_admission(self):
  public={r['dungeon']for r in RULES}
  from types import SimpleNamespace
  for dungeon in {r['dungeon']for r in STORY_RULES}-public:
   self.assertEqual(rules_for(SimpleNamespace(identity=dungeon)),tuple(r for r in STORY_RULES if r['dungeon']==dungeon))

if __name__=='__main__':unittest.main()
