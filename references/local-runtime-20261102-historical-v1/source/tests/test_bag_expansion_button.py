"""Inventory + entry, atomic debit/capacity, replay and cold restoration."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import sqlite3,struct,tempfile,unittest
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.bag_capacity import PRODUCT_GROUPS,capacity_map
from els_server.protocol import bag_expansion_messages as wire
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from els_server.storage.bag_capacity import direct_expansion,expansion_quote,expand


class BagExpansionButtonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('BagOther',5,'other')['uid']
        self.account.for_character(self.other)
        self.other_capacities=self.account.characters.get(self.other)['bag_capacities']
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=100000')
        self.session=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,
            gate_test=True,population_test=True,clear_test=True,reward_test=True,
            item_test=True,shop_test=True,client_build='dx11_260923')
        self.session.role='game';self.session.phase='town_ready'

    def request(self,kind,group,sequence):
        return self.session.handle(Event(0x202,kind=kind,payload=struct.pack('>i',group)),sequence)

    def quote(self,group):
        result=self.request(0x47b,group,1)
        self.assertEqual(result,[wire.quote_ack(50)])
        return self.session.bag_expansion_quotes[(1001,group)]

    def state(self):
        with closing(sqlite3.connect(self.path)) as db:
            return dict(capacities=self.account.character()['bag_capacities'],
                money=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=1001').fetchone(),
                receipt_count=db.execute('SELECT count(*) FROM inventory_action_receipts').fetchone()[0]
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone() else 0)

    def test_seven_tabs_quote_purchase_replay_and_cold_login(self):
        before=self.state()
        for seq,(template,group) in enumerate(PRODUCT_GROUPS.items(),2):
            self.quote(group)
            expected_ed=100000-50*(seq-1)
            self.assertEqual(self.request(0x479,group,seq),[wire.expansion_ack(group,expected_ed,8)])
            replay=self.request(0x479,group,seq)
            self.assertEqual(replay,[wire.expansion_ack(ed=expected_ed)])
        restored=LocalAccount(LocalState(self.path));restored.enable_characters()
        self.assertEqual(restored.character()['bag_capacities'],{**{g:44 for g in PRODUCT_GROUPS.values()}})
        self.assertEqual(restored.characters.get(self.other)['bag_capacities'],self.other_capacities)
        data=capacity_map(restored.character());n,=struct.unpack_from('>I',data)
        result=dict(struct.unpack_from('>ii',data,4+8*i) for i in range(n))
        self.assertTrue(all(result[g]==44 for g in PRODUCT_GROUPS.values()))
        after=self.state();self.assertEqual(after['money'],(99650,before['money'][1]+7));self.assertEqual(after['receipt_count'],7)

    def test_existing_44_slots_expand_to_52_and_new_slot_is_usable(self):
        with closing(sqlite3.connect(self.path)) as db,db:expand(db,1001,200753,1)
        self.quote(6);self.assertEqual(self.request(0x479,6,2),[wire.expansion_ack(6,99950,8)])
        self.assertEqual(self.account.character()['bag_capacities'],{6:52})
        from els_server.storage.inventory_state import grant_items,load_items
        from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
        with closing(sqlite3.connect(self.path)) as db,db:
            for _ in range(45):grant_items(db,[dict(template=77000,metadata=2,quantity=TEMPLATE_MAX_STACKS[77000],group=6)])
            self.assertEqual(load_items(db)[-1]['slot'],44)

    def test_no_quote_stale_quote_insufficient_money_and_limit(self):
        before=self.state()
        self.assertEqual(self.request(0x479,3,2),[wire.expansion_ack(result=-1)])
        self.assertEqual(self.state(),before)
        self.quote(3)
        with closing(sqlite3.connect(self.path)) as db,db:expand(db,1001,200754,1)
        changed=self.state();self.assertEqual(self.request(0x479,3,3),[wire.expansion_ack(result=-1)])
        self.assertEqual(self.state(),changed)
        self.quote(3)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=49 WHERE uid=1001')
        poor=self.state();self.assertEqual(self.request(0x479,3,4),[wire.expansion_ack(result=-1)])
        self.assertEqual(self.state(),poor)
        with closing(sqlite3.connect(self.path)) as db,db:
            expand(db,1001,200754,36);expand(db,1001,200754,7)
        full=self.state();self.assertEqual(full['capacities'][3],388)
        self.assertEqual(self.request(0x47b,3,5),[wire.quote_ack(result=-1)])
        self.assertEqual(self.request(0x479,3,6),[wire.expansion_ack(result=-1)])
        self.assertEqual(self.state(),full)

    def test_bad_category_payload_envelope_phase_and_lease_do_not_mutate(self):
        before=self.state()
        for group in (0,7,8,9,11,16,27,30,-1):
            self.assertEqual(self.request(0x47b,group,1),[wire.quote_ack(result=-1)])
        for payload in (b'',b'\3',bytes(5)):
            result=self.session.handle(Event(0x202,kind=0x47b,payload=payload),1)
            self.assertEqual(result,[wire.quote_ack(result=-1)])
        for seq in (None,0,True,2**32):
            self.assertEqual(self.request(0x47b,3,seq),[wire.quote_ack(result=-1)])
        for event in (Event(0x202,kind=0x47b,payload=struct.pack('>i',3),uid=1001),
                      Event(0x202,kind=0x47b,payload=struct.pack('>i',3),performers=(99,))):
            self.assertEqual(self.session.handle(event,1),[wire.quote_ack(result=-1)])
        self.session.phase='dungeon_active';self.assertEqual(self.request(0x47b,3,1),[wire.quote_ack(result=-1)])
        self.session.phase='town_ready'
        with patch('els_server.domain.bag_expansion_flow.current_lease',return_value=False):
            self.assertEqual(self.request(0x47b,3,1),[wire.quote_ack(result=-1)])
        self.assertEqual(self.state(),before)

    def test_encoding_and_commit_failure_roll_back_money_capacity_receipt(self):
        self.quote(3);before=self.state()
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('encode')):
            self.assertEqual(self.request(0x479,3,2),[wire.expansion_ack(result=-1)])
        self.assertEqual(self.state(),before)
        with patch('els_server.storage.inventory_actions._commit',side_effect=sqlite3.IntegrityError('receipt')):
            with self.assertRaises(sqlite3.IntegrityError):self.request(0x479,3,3)
        self.assertEqual(self.state(),before)
        self.assertEqual(self.request(0x479,3,4),[wire.expansion_ack(3,99950,8)])

    def test_concurrent_replay_conflict_owner_and_current_balance(self):
        expected=self.quote(3)
        def buy(_):return direct_expansion(self.path,1001,1,struct.pack('>i',3),'same',expected=expected,prepare=lambda db:None)
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(buy,range(2)))
        self.assertCountEqual(result,[wire.expansion_ack(3,99950,8),wire.expansion_ack(ed=99950)])
        self.assertEqual(self.state()['money'][0],99950);self.assertEqual(self.state()['receipt_count'],1)
        with self.assertRaises(ValueError):direct_expansion(self.path,1001,1,struct.pack('>i',4),'same',expected=expected,prepare=lambda db:None)
        with self.assertRaises(ValueError):direct_expansion(self.path,1001,2,struct.pack('>i',3),'foreign',expected=expected,prepare=lambda db:None)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=123 WHERE uid=1001')
        self.assertEqual(buy(0),wire.expansion_ack(ed=123))


if __name__=='__main__':unittest.main()
