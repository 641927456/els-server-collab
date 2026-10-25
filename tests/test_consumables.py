import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage.quick_slots import save_request,encode,empty,load
from els_server.storage.consumables import use
from els_server.protocol.protocol_codec import Event
from els_server.domain.consumables import ordinary,catalog

PAYLOAD=struct.pack('>HBBB',5,0,0,0)

class ConsumableTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('PotionOther',5,'other')['uid'];self.account.for_character(self.other)
        with closing(sqlite3.connect(self.path)) as db,db:grant_items(db,[dict(template=77000,metadata=2,quantity=2,group=6)])
        save_request(self.path,struct.pack('>i',1)+encode({**empty(),5:1}))

    def test_consumption_cooldown_replay_exhaustion_restart(self):
        balance=self.account.get_reward_balances();r=use(self.path,1001,PAYLOAD,'one',now=100)
        self.assertEqual([e.kind for e in r],[0x114,0x115]);self.assertEqual(len(r[0].payload),339)
        self.assertEqual(r[1].payload,struct.pack('>Qi?Q?',1001,77000,False,0,False))
        self.assertEqual(self.account.get_inventory_snapshot()['items'][0]['count'],1)
        replay=use(self.path,1001,PAYLOAD,'one',now=101)
        self.assertEqual(len(replay),1);self.assertEqual(struct.unpack_from('>i',replay[0].payload,328)[0],-1)
        with self.assertRaises(ValueError):use(self.path,1001,PAYLOAD,'too-soon',now=129.9)
        restarted=LocalAccount(LocalState(self.path));restarted.enable_characters()
        use(restarted.store.path,1001,PAYLOAD,'two',now=130)
        self.assertEqual(self.account.get_inventory_snapshot()['items'],[])
        self.assertEqual(load(self.path)[5],1);self.assertEqual(self.account.get_reward_balances(),balance)
        self.assertEqual(len(use(self.path,1001,PAYLOAD,'one',now=200)),1)
        with self.assertRaises(ValueError):use(self.path,1001,PAYLOAD,'empty',now=200)

    def test_invalid_owner_modes_conflict_and_rollback(self):
        before=self.account.get_inventory_snapshot()
        for payload in (b'',PAYLOAD[:-1],PAYLOAD+b'\0',struct.pack('>HBBB',6,0,0,0),struct.pack('>HBBB',5,1,0,0)):
            with self.assertRaises(ValueError):use(self.path,1001,payload,'invalid',now=1)
        for owner in (self.other,99999):
            with self.assertRaises(ValueError):use(self.path,owner,PAYLOAD,'foreign',now=1)
        with patch('els_server.storage.consumables.effect',side_effect=RuntimeError('encoder failure')):
            with self.assertRaises(RuntimeError):use(self.path,1001,PAYLOAD,'fail',now=1)
        self.assertEqual(self.account.get_inventory_snapshot(),before)
        use(self.path,1001,PAYLOAD,'good',now=1)
        with self.assertRaises(ValueError):use(self.path,1001,struct.pack('>HBBB',4,0,0,0),'good',now=40)

    def test_concurrent_uses_share_cooldown_atomically(self):
        def attempt(n):
            try:return use(self.path,1001,PAYLOAD,str(n),now=500)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[1,2]))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.account.get_inventory_snapshot()['items'][0]['count'],1)

    def test_dispatch_phase_and_catalog_scope(self):
        self.assertEqual(len(catalog()),918)
        for t in (77000,77010):self.assertEqual(ordinary(t)['cooldown_seconds'],30)
        with self.assertRaises(ValueError):ordinary(77020)
        with self.assertRaises(ValueError):ordinary(78000)
        s=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,client_build='dx11_260923');s.role='game';s.phase='characters_ready'
        event=Event(0x202,kind=0x113,payload=PAYLOAD)
        self.assertEqual(s.handle(event,1)[0].payload[:4],struct.pack('>i',-1))
        s.phase='town_ready'
        self.assertEqual(s.handle(event,2)[0].payload[:4],struct.pack('>i',-1))
        s.phase='dungeon_active'
        self.assertEqual([e.kind for e in s.handle(event,2)],[0x114,0x115])
        self.assertEqual([e.kind for e in s.handle(event,2)],[0x114])

    def test_mana_potion_has_independent_cooldown_group(self):
        from els_server.domain.quick_bindings import item_binding
        with closing(sqlite3.connect(self.path)) as db,db:grant_items(db,[dict(template=77010,metadata=2,quantity=2,group=6)])
        save_request(self.path,struct.pack('>i',1)+encode({**empty(),5:1,4:item_binding(77010)}))
        use(self.path,1001,PAYLOAD,'hp',now=100)
        answer=use(self.path,1001,struct.pack('>HBBB',4,0,0,0),'mp',now=100)
        self.assertEqual(struct.unpack_from('>i',answer[1].payload,8)[0],77010)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT cooldown_group,ready_at FROM consumable_cooldowns ORDER BY cooldown_group').fetchall(),[(1,130.0),(4,130.0)])

    def test_higher_potions_share_native_groups_and_keep_sixty_seconds(self):
        from els_server.domain.quick_bindings import item_binding
        for template in (77170,77180,77190,77270,78902):
            with closing(sqlite3.connect(self.path)) as db,db:grant_items(db,[dict(template=template,metadata=2,quantity=2,group=6)])
        values={**empty(),0:1,1:item_binding(77170),2:item_binding(77190),3:item_binding(77270),4:item_binding(77180),5:item_binding(78902)}
        save_request(self.path,struct.pack('>i',1)+encode(values))
        use(self.path,1001,struct.pack('>HBBB',0,0,0,0),'basic-hp',now=100)
        for slot in (1,2,3):
            with self.assertRaises(ValueError):use(self.path,1001,struct.pack('>HBBB',slot,0,0,0),'shared-'+str(slot),now=129)
        for slot,template in ((1,77170),(2,77190),(3,77270)):
            answer=use(self.path,1001,struct.pack('>HBBB',slot,0,0,0),'higher-'+str(slot),now=100+30*slot)
            self.assertEqual(struct.unpack_from('>i',answer[1].payload,8)[0],template)
        use(self.path,1001,struct.pack('>HBBB',4,0,0,0),'middle-mp',now=200)
        use(self.path,1001,struct.pack('>HBBB',5,0,0,0),'upper-mp',now=200)
        with self.assertRaises(ValueError):use(self.path,1001,struct.pack('>HBBB',5,0,0,0),'upper-early',now=259)
        use(self.path,1001,struct.pack('>HBBB',5,0,0,0),'upper-again',now=260)
        with self.assertRaises(ValueError):ordinary(78925)
