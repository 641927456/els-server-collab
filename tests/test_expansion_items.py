"""Native-use coupon: atomic consume/unlock, ownership, replay and bag reconciliation."""
import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.inventory_state import grant_items
from els_server.storage.expansion_items import use_expansion_item,ORDINARY_COUPON
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import Event


class ExpansionItemTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('OtherEve',5,'other')
        with closing(sqlite3.connect(self.path)) as db,db:
            self.item=grant_items(db,[dict(template=ORDINARY_COUPON,metadata=0,group=4,quantity=1)])[0]
        self.payload=struct.pack('>QQiiIB',self.item['uid'],0,0,0,0,0)

    def session(self,account=None):
        s=LocalSession(account or self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,client_build='dx11_260923')
        s.role='game';s.phase='town_ready';return s

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def test_native_dispatch_and_restart(self):
        s=self.session();event=Event(0x202,kind=0x219,payload=self.payload)
        balances=self.account.get_reward_balances();responses=s.handle(event,1)
        self.assertEqual([r.kind for r in responses],[0x21a,0x12f])
        self.assertEqual(struct.unpack_from('>i',responses[0].payload)[0],0)
        self.assertEqual(self.account.get_inventory_snapshot()['items'],[])
        self.assertEqual(self.account.get_reward_balances(),balances)
        self.assertTrue(self.account.character()['skill_row_expanded'])
        self.assertFalse(self.account.characters.get(self.other['uid'])['skill_row_expanded'])
        before=self.dump();replay=s.handle(event,1);self.assertEqual(self.dump(),before)
        self.assertEqual([r.kind for r in replay],[0x21a,0x12f])
        restored=LocalAccount(LocalState(self.path));restored.enable_characters()
        self.assertTrue(restored.character()['skill_row_expanded'])
        restored.equip_skill(struct.pack('>ii',7,21000))

    def test_replay_reconciles_reused_slot(self):
        use_expansion_item(self.path,1001,self.payload,'once')
        with closing(sqlite3.connect(self.path)) as db,db:
            replacement=grant_items(db,[dict(template=274333,metadata=VERIFIED_TEMPLATES[274333],group=4,quantity=3)])[0]
            db.execute('UPDATE reward_balances SET ed=123 WHERE uid=1001')
        before=self.dump();result=use_expansion_item(self.path,1001,self.payload,'once')
        self.assertEqual(self.dump(),before)
        self.assertEqual(result['response'],use_ack([((4,self.item['slot']),replacement)],ed=123).payload)

    def test_rollback_concurrency_and_no_second_consume(self):
        before=self.dump()
        with patch('els_server.storage.expansion_items.use_ack',side_effect=ValueError('Encoding failed')):
            with self.assertRaises(ValueError):use_expansion_item(self.path,1001,self.payload,'bad')
        self.assertEqual(self.dump(),before)
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(lambda _:use_expansion_item(self.path,1001,self.payload,'same'),range(2)))
        self.assertEqual(sorted(r['replayed'] for r in result),[False,True])
        with closing(sqlite3.connect(self.path)) as db,db:
            other=grant_items(db,[dict(template=ORDINARY_COUPON,metadata=0,group=4,quantity=2)])[0]
        payload=struct.pack('>QQiiIB',other['uid'],0,0,0,0,0);before=self.dump()
        with self.assertRaises(ValueError):use_expansion_item(self.path,1001,payload,'second')
        with self.assertRaises(ValueError):use_expansion_item(self.path,1001,payload,'same')
        self.assertEqual(self.dump(),before)

    def test_foreign_item_and_malformed_use_do_not_unlock(self):
        s=self.session(self.account.for_character(self.other['uid']))
        for payload in (self.payload,self.payload[:-1],struct.pack('>QQiiIB',self.item['uid'],0,1,0,0,0)):
            reply=s.handle(Event(0x202,kind=0x219,payload=payload),1)
            self.assertEqual(len(reply),1);self.assertNotEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
        self.assertFalse(self.account.character()['skill_row_expanded'])
        self.assertEqual(self.account.get_inventory_snapshot()['items'],[self.item])

    def test_before_scene_ready_is_rejected_without_consuming(self):
        s=self.session();s.phase='square_accepted';before=self.dump()
        response=s.handle(Event(0x202,kind=0x219,payload=self.payload),1)
        self.assertEqual([r.kind for r in response],[0x21a])
        self.assertNotEqual(struct.unpack_from('>i',response[0].payload)[0],0)
        self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main()
