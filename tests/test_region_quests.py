"""Native region gates: class/level restrictions and actual task completion."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.region_quests import RegionQuestCatalog,region_catalog,sequence

class RegionQuestTests(unittest.TestCase):
    def test_every_region_task_has_real_prior_chain_and_clear_target(self):
        c=region_catalog();ids=sorted(c.quest_definitions());self.assertEqual(len(ids),13)
        completed=set()
        for i in ids:
            q=c.quest_definitions()[i]
            self.assertTrue(set(sequence(q['QuestCondition']['m_vecBeforeQuestID']))<=completed)
            for sid in sequence(q['m_vecSubQuest']):
                sub=c.subquest_definitions()[sid]
                self.assertIn(sub['m_eClearType'],(8,32))
                self.assertEqual(sub['m_ClearCondition']['m_iDungeonClearCount'],1)
                self.assertTrue(sequence(sub['m_ClearCondition']['m_eDungeonID']))
            completed.add(i)
        self.assertEqual(c.quest_definitions()[26640]['m_vecSubQuest']['1'],22363)
        self.assertEqual(c.quest_definitions()[27550]['m_vecSubQuest']['1'],27540)
        self.assertEqual(c.quest_definitions()[27580]['m_vecSubQuest']['1'],27570)

    def test_completion_changes_all_devil_region_gates(self):
        c=region_catalog();character=dict(level=99,unit_type=1)
        for region,row in c.data['regions'].items():
            task=row['requirement'].get('RequireQuestID')
            if not task:continue
            self.assertFalse(c.region_allowed(int(region),character,set()))
            self.assertFalse(c.region_allowed(int(region),character,{task+1}))
            self.assertTrue(c.region_allowed(int(region),character,{task}))
            self.assertFalse(c.region_allowed(int(region),dict(character,level=98),{task}))
        self.assertFalse(c.dungeon_allowed(34090,character,set()))
        self.assertTrue(c.dungeon_allowed(34090,character,{26640}))

    def test_native_character_and_level_restrictions(self):
        c=region_catalog()
        self.assertFalse(c.region_allowed(10001,dict(level=5,unit_type=1),set()))
        self.assertTrue(c.region_allowed(10001,dict(level=6,unit_type=1),set()))
        for unit in (13,14):
            self.assertFalse(c.region_allowed(10001,dict(level=69,unit_type=unit),set()))
            self.assertTrue(c.region_allowed(10001,dict(level=70,unit_type=unit),set()))
        self.assertFalse(c.region_allowed(10001,dict(level=98,unit_type=15),set()))
        self.assertTrue(c.region_allowed(10001,dict(level=99,unit_type=15),set()))
        self.assertFalse(c.region_allowed(10017,dict(level=99,unit_type=1),set()))
        self.assertTrue(c.region_allowed(10017,dict(level=1,unit_type=13),set()))
        self.assertTrue(c.region_allowed(10025,dict(level=39,unit_type=14),set()))
        self.assertFalse(c.region_allowed(10025,dict(level=40,unit_type=14),set()))
        self.assertFalse(c.region_allowed(10026,dict(level=39,unit_type=14),set()))
        self.assertTrue(c.region_allowed(10026,dict(level=40,unit_type=14),set()))
        # Last native registration overrides the old secret-dungeon level70.
        self.assertFalse(c.region_allowed(10015,dict(level=98,unit_type=1),set()))
        self.assertTrue(c.region_allowed(10015,dict(level=99,unit_type=1),set()))

    def test_excluded_and_event_dungeons_cannot_use_a_region_default(self):
        c=region_catalog();scope=json.loads((ROOT/'config/dungeon_scope.json').read_text(encoding='utf8'))
        completed=set(c.data['roots']);character=dict(level=99,unit_type=1)
        for i in [*scope['excluded'],*scope['pending']]:
            self.assertFalse(c.dungeon_allowed(int(i),character,completed))
        self.assertFalse(c.dungeon_allowed(True,character,completed))
        self.assertFalse(c.dungeon_allowed('34090',character,completed))

    def test_tampered_catalog_fails_before_use(self):
        from els_server.game_data import DATA_DIR
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            for n in ('region_quests.json','region_quests.manifest.json'):(dest/n).write_bytes((DATA_DIR/n).read_bytes())
            (dest/'region_quests.json').write_bytes((dest/'region_quests.json').read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'identity'):RegionQuestCatalog(dest)

if __name__=='__main__':unittest.main()
