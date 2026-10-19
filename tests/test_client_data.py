"""Client definitions drive progression without corrupting saves or inventing loot."""
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.game_data import ClientData,client_data
from els_server.domain.character_rules import INITIAL,CLASSES,default_slots
from els_server.domain.skill_rules import learned_skills,equippable_skills,upgraded_slots
from els_server.domain.character_stats import relative_attributes,equipment_attributes,combat_values
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.reward_state import RewardConflict
from els_server.domain.reward_rules import dungeon_rewards,drop_reference,item_plan
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,FASHION_EQUIP_SLOTS


class ClientDataTests(unittest.TestCase):
    def test_readonly_and_detached_results(self):
        data=client_data()
        with data.connect() as db:
            with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM items')
        skill=data.skill(25000);skill['m_eID']=0
        self.assertEqual(data.skill(25000)['m_eID'],25000)
        with self.assertRaises(ValueError):data.item(-1)
        self.assertEqual(data.manifest['counts']['items'],181836)

    def test_all_ordinary_level_boundaries(self):
        data=client_data()
        for level,needed,total in data.experience:
            self.assertEqual(data.level_for_experience(total),level)
            if level>1:self.assertEqual(data.level_for_experience(total-1),level-1)
        self.assertEqual(data.level_for_experience(2**31-1),99)
        for bad in (-1,True,1.5):
            with self.assertRaises(ValueError):data.level_for_experience(bad)

    def test_level_transaction_rollback_retry_and_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
            second=account.characters.create('TestEve',5,'create')
            rewards=account.reward_store;run=str(uuid.uuid4())
            receipt=rewards.grant(run,b'clear',120,600,lambda balance:b'encoded')
            self.assertEqual(account.character()['level'],2)
            self.assertEqual(account.characters.get(second['uid'])['level'],1)
            self.assertTrue(rewards.grant(run,b'clear',120,600,lambda _:self.fail('Replay encoded again'))['replayed'])
            self.assertEqual(rewards.balances(),receipt['balances'])
            with self.assertRaises(RewardConflict):rewards.grant(run,b'clear',120,601,lambda _:b'x')
            before=account.character()
            def fail(_):raise RuntimeError('encoder failure')
            with self.assertRaises(RuntimeError):rewards.grant(str(uuid.uuid4()),b'clear2',120,100000,fail)
            self.assertEqual(account.character(),before)
            self.assertEqual(rewards.balances(),receipt['balances'])
            target=client_data().thresholds[9]
            rewards.grant(str(uuid.uuid4()),b'clear3',0,target-600,lambda _:b'encoded')
            self.assertEqual(account.character()['level'],10)
            restored=LocalAccount(LocalState(path));restored.enable_characters()
            self.assertEqual(restored.character()['level'],10)
            self.assertIn(21002,equippable_skills(restored.character()))

    def test_career_transition_persists_skill_replacement(self):
        from els_server.domain.careers import RULES
        from els_server.storage.inventory_state import grant_items
        from els_server.storage.careers import use_career_item
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
            account.reward_store.grant(str(uuid.uuid4()),b'level',0,client_data().thresholds[14],lambda _:b'ok')
            account.save_skills((21000,21200)+(0,)*20)
            template,rule=next((t,r) for t,r in RULES.items() if r['kind']=='advancement_1' and r['unit_type']==1)
            with closing(sqlite3.connect(path)) as db,db:
                item=grant_items(db,[item_plan(template,1)],1001)[0]
            payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
            use_career_item(path,1001,payload,'promotion')
            self.assertEqual(account.get_skills()[0],21026)
            restored=LocalAccount(LocalState(path));restored.enable_characters()
            self.assertEqual(restored.get_skills(),account.get_skills())

    def test_skill_requirements_and_upgrades(self):
        for cls,ids in INITIAL.items():
            self.assertEqual(set(learned_skills(dict(unit_class=cls,level=1))),set(ids))
        self.assertNotIn(25001,learned_skills(dict(unit_class=5,level=4)))
        self.assertIn(25001,learned_skills(dict(unit_class=5,level=5)))
        self.assertNotIn(21000,learned_skills(dict(unit_class=5,level=99)))
        self.assertNotIn(21201,learned_skills(dict(unit_class=1,level=99)))  # sealed
        first=next(cls for cls,v in CLASSES.items() if v==dict(base_class=1,stage=1))
        c=dict(unit_class=first,level=15)
        self.assertIn(21026,learned_skills(c));self.assertNotIn(21000,learned_skills(c))
        self.assertEqual(upgraded_slots((21000,21200)+(0,)*20,c)[0],21026)
        self.assertNotIn(21037,learned_skills(dict(unit_class=100,level=99)))
        self.assertIn(21037,learned_skills(dict(unit_class=100,level=99,transcendence=True)))
        for cls in CLASSES:
            c=dict(unit_class=cls,level=99,transcendence=CLASSES[cls]['stage']>=2)
            self.assertTrue(set(default_slots(c))-{0}<=set(equippable_skills(c)))
            for skill in equippable_skills(c):self.assertNotEqual(client_data().skill(skill)['m_eType'],8)

    def test_native_formula_witnesses(self):
        rows=json.loads((ROOT/'analysis/client-data-20261015/stat-formula-native-proof.json').read_text(encoding='utf8'))
        self.assertGreaterEqual(len(rows),10)
        for row in rows:
            self.assertFalse(row['applied_to_game'])
            self.assertEqual(list(relative_attributes(row['A'],row['B'],row['C'],row['spec'][3],row.get('extra',[0]*6))),row['result'])

    def test_inventory_catalog_and_equipment(self):
        for template,metadata in VERIFIED_TEMPLATES.items():
            self.assertEqual(client_data().item(template)['metadata'],metadata)
        c=dict(unit_class=1,unit_type=1,level=1)
        item=dict(uid=1001001,template=81021,metadata=0,count=1,group=9,slot=FASHION_EQUIP_SLOTS[81021])
        self.assertEqual(equipment_attributes(81021,c),(0,10,10,0,0,5,5))
        self.assertEqual(tuple(a-b for a,b in zip(combat_values(c,[item]),combat_values(c))),equipment_attributes(81021,c))
        self.assertEqual(combat_values(c,[dict(item,group=27,slot=0)]),combat_values(c))

    def test_loot_policy_is_not_display_pool(self):
        rule=dungeon_rewards(30000);reference=drop_reference(30000)
        self.assertEqual(rule['provenance'],'local_policy')
        self.assertFalse(reference['probabilities_available'])
        self.assertEqual(rule['clear_items'][0]['template'],77000)
        self.assertEqual(rule['clear_items'][0]['quantity'],3)
        with self.assertRaises(ValueError):dungeon_rewards(-1)
        with self.assertRaises(ValueError):item_plan(-1,1)


if __name__=='__main__':unittest.main()
