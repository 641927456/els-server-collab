import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.shop_state import purchase
from els_server.storage.inventory_state import grant_items,load_items,InventoryFull
from els_server.domain.bag_capacity import PRODUCT_GROUPS,capacities,capacity_map
from els_server.protocol.protocol_codec import Event

def request(template,quantity=1):return struct.pack('>IIH',1,1200000000+template,quantity)

class BagCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('BagOther',5,'other')['uid']
        self.account.for_character(self.other)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=100000')

    def test_six_products_character_isolation_restart_and_wire(self):
        s=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,shop_test=True,client_build='dx11_260923')
        s.role='game';s.phase='town_ready';s.ed_catalog_loaded=True
        before=self.account.get_inventory_snapshot()['items']
        for seq,(template,group) in enumerate(PRODUCT_GROUPS.items(),1):
            event=Event(0x202,kind=0x80f,payload=request(template))
            result=s.handle(event,seq)
            self.assertEqual([e.kind for e in result],[0x810,0x26c])
            self.assertEqual(result[1].payload,struct.pack('>Iii',1,group,8)+bytes(12))
            self.assertEqual([e.kind for e in s.handle(event,seq)],[0x810])
        self.assertEqual(self.account.get_inventory_snapshot()['items'],before)
        self.assertEqual(self.account.get_reward_balances()['ed'],99700)
        restored=LocalAccount(LocalState(self.path));restored.enable_characters()
        self.assertEqual(restored.character()['bag_capacities'],{g:44 for g in range(1,7)})
        self.assertEqual(restored.characters.get(self.other)['bag_capacities'],{})
        wire=capacity_map(restored.character())
        n=struct.unpack_from('>I',wire)[0]
        self.assertEqual(dict(struct.unpack_from('>ii',wire,4+8*i) for i in range(n)),capacities(restored.character())|{8:8,16:8})

    def test_new_slots_are_usable_and_unowned_slots_rejected(self):
        potion=dict(template=77000,metadata=2,quantity=99,group=6)
        with closing(sqlite3.connect(self.path)) as db,db:
            for _ in range(36):grant_items(db,[potion])
        with closing(sqlite3.connect(self.path)) as db,db:
            with self.assertRaises(InventoryFull):grant_items(db,[potion])
        purchase(self.path,request(200753),'expand')
        with closing(sqlite3.connect(self.path)) as db,db:
            added=grant_items(db,[potion]);self.assertEqual(added[0]['slot'],36)
            self.assertEqual(len(load_items(db)),37)
            db.execute('UPDATE inventory_items SET slot=44 WHERE uid=?',(added[0]['uid'],))
            with self.assertRaises(ValueError):load_items(db)
            db.rollback()

    def test_limit_rollback_funds_and_concurrent_replay(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(lambda _:purchase(self.path,request(200751),'same'),range(2)))
        self.assertEqual(rows[0],rows[1])
        self.assertEqual(self.account.character()['bag_capacities'],{1:44})
        purchase(self.path,request(200751,36),'bulk')
        purchase(self.path,request(200751,7),'ceiling')
        self.assertEqual(self.account.character()['bag_capacities'][1],388)
        before=self.account.get_reward_balances()
        with self.assertRaises(ValueError):purchase(self.path,request(200751),'overflow')
        self.assertEqual(self.account.get_reward_balances(),before)
        mixed=struct.pack('>IIHIH',2,1200200754,1,880000,1)
        with patch('els_server.storage.shop_state.grant_items',side_effect=InventoryFull('full')):
            with self.assertRaises(InventoryFull):purchase(self.path,mixed,'rollback')
        self.assertNotIn(3,self.account.character()['bag_capacities'])
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=49 WHERE uid=1001')
        with self.assertRaises(ValueError):purchase(self.path,request(200752),'poor')
        self.assertNotIn(2,self.account.character()['bag_capacities'])
        replay=purchase(self.path,request(200751),'same')
        self.assertEqual(struct.unpack('>Q',replay[-8:])[0],49)

