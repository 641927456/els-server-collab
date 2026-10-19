"""Permanent expansion survives replay/reconnect without granting other slots."""
import sqlite3,struct,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.shop_state import purchase,catalog
from els_server.domain.skill_expansion import ORDINARY_SKU,records
from els_server.protocol.protocol_codec import Event
from els_server.protocol.dungeon_messages import skill_data


class SkillExpansionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('OtherEve',5,'other')
        self.account.for_character(self.other['uid'])
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=500')
        self.payload=struct.pack('>IIH',1,ORDINARY_SKU,1)

    def test_purchase_equip_reconnect_and_character_isolation(self):
        session=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,shop_test=True,item_test=True,client_build='dx11_260923')
        session.role='game';session.phase='town_ready';session.ed_catalog_loaded=True
        event=Event(0x202,kind=0x80f,payload=self.payload)
        before=self.account.get_inventory_snapshot()['items']
        result=session.handle(event,11)
        self.assertEqual([e.kind for e in result],[0x810,0x12f])
        self.assertEqual(result[1].payload,struct.pack('>QiiIB',1001,0,2,0,1))
        self.assertEqual(session.handle(event,11),result)
        self.assertEqual(self.account.get_reward_balances()['ed'],450)
        self.assertEqual(self.account.get_inventory_snapshot()['items'],before)
        self.assertTrue(self.account.character()['skill_row_expanded'])
        self.assertFalse(self.account.characters.get(self.other['uid'])['skill_row_expanded'])
        ack=self.account.equip_skill(struct.pack('>ii',7,21000))
        self.assertEqual(struct.unpack('>5i',ack),(0,7,21000,0,0))
        restored=LocalAccount(LocalState(self.path));restored.enable_characters()
        self.assertEqual(restored.get_skills()[7],21000)
        self.assertEqual(skill_data(restored.get_skills(),restored.character())[224:252],records(restored.character()))
        for index in (4,9,10,21):
            with self.assertRaises(ValueError):restored.equip_skill(struct.pack('>ii',index,21000))
        for index in (5,6,7,8):
            restored.equip_skill(struct.pack('>ii',index,21000))
            self.assertEqual(restored.get_skills()[index],21000)
        with self.assertRaises(ValueError):self.account.for_character(self.other['uid']).equip_skill(struct.pack('>ii',5,21000))
        with self.assertRaises(ValueError):purchase(self.path,self.payload,'repeat')
        self.assertEqual(self.account.get_reward_balances()['ed'],450)

    def test_atomic_failure_and_concurrent_retry(self):
        normal=next(p for p in catalog() if p['sku']!=ORDINARY_SKU)
        mixed=struct.pack('>IIHIH',2,ORDINARY_SKU,1,normal['sku'],1)
        with patch('els_server.storage.shop_state.grant_items',side_effect=ValueError('Bag capacity')):
            with self.assertRaises(ValueError):purchase(self.path,mixed,'rollback')
        self.assertFalse(self.account.character()['skill_row_expanded'])
        self.assertEqual(self.account.get_reward_balances()['ed'],500)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:purchase(self.path,self.payload,'same'),range(2)))
        self.assertEqual(responses[0],responses[1])
        self.assertEqual(self.account.get_reward_balances()['ed'],450)
        with closing(sqlite3.connect(self.path)) as db,db:
            self.assertEqual(db.execute('SELECT count(*) FROM character_skill_expansions').fetchone()[0],1)
            db.execute('UPDATE reward_balances SET ed=300 WHERE uid=1001')
        replay=purchase(self.path,self.payload,'same')
        self.assertEqual(struct.unpack('>Q',replay[-8:])[0],300)
        self.assertEqual(self.account.get_reward_balances()['ed'],300)

    def test_invalid_quantity_and_funds_do_not_unlock(self):
        with self.assertRaises(ValueError):purchase(self.path,struct.pack('>IIH',1,ORDINARY_SKU,2),'two')
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=49 WHERE uid=1001')
        with self.assertRaises(ValueError):purchase(self.path,self.payload,'poor')
        self.assertFalse(self.account.character()['skill_row_expanded'])
        self.assertEqual(self.account.get_reward_balances()['ed'],49)

    def test_career_keeps_expanded_layout(self):
        from els_server.domain.careers import RULES
        from els_server.storage.careers import use_career_item
        from els_server.storage.inventory_state import grant_items
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES
        purchase(self.path,self.payload,'unlock')
        self.account.equip_skill(struct.pack('>ii',7,21000))
        template,rule=next((t,r) for t,r in RULES.items() if r['kind']=='advancement_1' and r['unit_type']==1)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=15 WHERE uid=1001')
            item=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],quantity=1,group=4)],1001)[0]
        request=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
        use_career_item(self.path,1001,request,'career')
        restored=LocalAccount(LocalState(self.path));restored.enable_characters()
        self.assertTrue(restored.character()['skill_row_expanded'])
        self.assertEqual(restored.character()['unit_class'],rule['target'])
        self.assertNotEqual(restored.get_skills()[7],0)
        self.assertEqual(self.account.get_reward_balances()['ed'],450)


if __name__=='__main__':unittest.main()
