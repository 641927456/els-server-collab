"""Real temp-save transactions for account bank and native ED expansion flows."""
import sqlite3,struct,unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_bank_state import payload
from els_server.storage.bank_state import transfer,sort,snapshot,quote,expand,contents
from els_server.storage.inventory_state import load_items
from els_server.domain.local_session import LocalSession,LocalAccount
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event
from els_server.domain.bank_rules import ED_COSTS


class SharedBankTests(unittest.TestCase):
    setUp=fixture.SaleTests.setUp
    grant=fixture.SaleTests.grant
    items=fixture.SaleTests.items
    dump=fixture.SaleTests.dump
    money=fixture.SaleTests.money

    def shared(self,owner=1001):
        return [e for e in snapshot(self.path,owner)['bank_items'] if e['position'][0]==16]

    def deposit(self,item,slot=0,quantity=None,operation='shared'):
        return transfer(self.path,1001,payload((item['group'],item['slot']),(16,slot),item,quantity),operation)

    def fund(self):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=1000000000 WHERE uid=1001')

    def test_cross_character_exact_instance_withdrawal_and_relog(self):
        from els_server.storage.equipment_enhancement import replace
        from els_server.storage.item_expiration import assign
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');replace(db,1001,self.gear['uid'],0,3);assign(db,1001,self.gear['uid'],2200000000)
        item=next(i for i in self.items() if i['uid']==self.gear['uid']);self.deposit(item)
        self.assertEqual(self.shared()[0]['item'],item)
        self.assertEqual(self.shared(self.other),self.shared())
        transfer(self.path,self.other,payload((16,0),(1,35),item),'other-withdraw')
        self.assertEqual(self.shared(),[])
        with closing(sqlite3.connect(self.path)) as db:
            restored=next(i for i in load_items(db,self.other) if i['uid']==item['uid'])
        self.assertEqual(restored,dict(item,slot=35))
        restored_account=LocalAccount(LocalState(self.path));restored_account.enable_characters()
        self.assertEqual(restored_account.character()['bank_capacities'],{8:8,16:8})

    def test_account_isolation_including_receipts(self):
        self.deposit(self.gear)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE character_owners SET account_id=2 WHERE uid=?',(self.other,))
        self.assertEqual(self.shared(self.other),[])
        before=self.dump()
        with self.assertRaises(ValueError):transfer(self.path,self.other,payload((16,0),(1,35),self.gear),'foreign')
        self.assertEqual(self.dump(),before);self.assertEqual(len(self.shared()),1)

    def test_partial_split_merge_private_shared_swap_and_sort(self):
        item=self.grant(701000,20);self.deposit(item,5,7)
        bank=self.shared()[0]['item'];self.assertNotEqual(bank['uid'],item['uid'])
        transfer(self.path,1001,payload((16,5),(8,2),bank,3),'to-private')
        transfer(self.path,1001,payload((8,2),(16,5),dict(bank,count=3)),'merge-back')
        self.assertEqual(self.shared()[0]['item']['count'],7)
        self.deposit(self.gear,1,operation='gear')
        wire=sort(self.path,1001,struct.pack('>i',16),'sort-shared')
        self.assertEqual(struct.unpack_from('>iI',wire),(16,2))
        self.assertEqual([e['position'] for e in self.shared()],[(16,0),(16,1)])
        before=self.dump();self.assertEqual(sort(self.path,self.other,struct.pack('>i',16),'sort-other')[:8],wire[:8])

    def test_double_withdraw_from_two_characters_conserves_uid(self):
        self.deposit(self.gear)
        def take(owner):
            try:transfer(self.path,owner,payload((16,0),(1,35),self.gear),'take-'+str(owner));return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(take,(1001,self.other))),1)
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory_items WHERE uid=?',(self.gear['uid'],)).fetchone(),(1,))

    def test_retry_after_sibling_withdraw_does_not_resurrect(self):
        p=payload((1,self.gear['slot']),(16,0),self.gear)
        transfer(self.path,1001,p,'deposit-once')
        transfer(self.path,self.other,payload((16,0),(1,35),self.gear),'take')
        before=self.dump();wire=transfer(self.path,1001,p,'deposit-once')
        self.assertEqual(self.dump(),before);self.assertEqual(self.shared(),[])
        self.assertEqual(struct.unpack_from('>Q',wire,4+324)[0],0)

    def test_complete_expansion_ladder_money_scope_and_retry(self):
        self.fund();spent=0
        for group in (8,16):
            for tier,cost in zip((8,16,24,32,40),ED_COSTS[group]):
                op=f'expand-{group}-{tier}';self.assertEqual(quote(self.path,1001,group),(tier,cost))
                wire=expand(self.path,1001,group,b'',op,(tier,cost));spent+=cost
                self.assertEqual(struct.unpack_from('>iQIii',wire),(0,1_000_000_000-spent,1,group,8))
                self.assertEqual(snapshot(self.path,1001)['bank_capacities'][group],tier+8)
                repeat=expand(self.path,1001,group,b'',op)
                self.assertEqual(struct.unpack_from('>iQI',repeat),(0,1_000_000_000-spent,0))
            with self.assertRaises(ValueError):quote(self.path,1001,group)
        self.assertEqual(snapshot(self.path,self.other)['bank_capacities'],{8:8,16:48})
        self.assertEqual(self.money(),1_000_000_000-spent)

    def test_missing_stale_quote_funds_max_and_encoding_failure_rollback(self):
        before=self.dump()
        for expected in (None,(16,16_000_000),(8,7)):
            with self.assertRaises(ValueError):expand(self.path,1001,16,b'','invalid',expected)
            self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):expand(self.path,1001,16,b'','poor',quote(self.path,1001,16))
        self.assertEqual(self.dump(),before);self.fund();before=self.dump()
        with patch('els_server.protocol.bank_messages.expansion_ack',side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):expand(self.path,1001,16,b'','encode',quote(self.path,1001,16))
        self.assertEqual(self.dump(),before)
        stale=quote(self.path,1001,16);expand(self.path,1001,16,b'','first',stale)
        before=self.dump()
        with self.assertRaises(ValueError):expand(self.path,self.other,16,b'','stale-other',stale)
        self.assertEqual(self.dump(),before)

    def test_concurrent_expansion_retry_and_newly_available_slot(self):
        self.fund();q=quote(self.path,1001,16)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:expand(self.path,1001,16,b'','same',q),range(2)))
        self.assertEqual(sorted(struct.unpack_from('>I',r,12)[0] for r in results),[0,1])
        self.assertEqual(self.money(),992_000_000)
        self.deposit(self.gear,15)
        self.assertEqual(self.shared()[0]['position'],(16,15))
        with self.assertRaises(ValueError):self.deposit(self.grant(30160),16,operation='over')

    def test_locked_shared_deposit_and_uid_reservation(self):
        from els_server.storage.item_locks import assign
        from els_server.storage.item_instances import uid_in_use
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,1001,self.gear['uid'],2100000000)
        before=self.dump()
        with self.assertRaises(ValueError):self.deposit(self.gear)
        self.assertEqual(self.dump(),before)
        item=self.grant(701000);self.deposit(item)
        with closing(sqlite3.connect(self.path)) as db:self.assertTrue(uid_in_use(db,item['uid']))

    def test_shared_expiration_removes_once_across_characters(self):
        from els_server.storage.item_expiration import assign
        from els_server.storage.bank_state import remove_due
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,1001,self.gear['uid'],2200000000)
        self.deposit(self.gear)
        with patch('els_server.domain.item_expiration.time.time',return_value=2300000000):
            self.assertEqual(self.shared(self.other),[])
            result=remove_due(self.path,self.other);self.assertEqual(result[0].kind,0x105)
            self.assertEqual(remove_due(self.path,1001),[])
            with self.assertRaises(ValueError):transfer(self.path,self.other,payload((16,0),(1,35),self.gear),'expired-shared')

    def test_native_session_query_expand_open_and_malformed_paths(self):
        self.fund();session=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,
            gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,client_build='dx11_260923')
        session.role='game';session.phase='town_ready'
        for group,qkind,ekind in ((8,0x477,0x475),(16,0x54b,0x54d)):
            first=session.handle(Event(0x202,kind=ekind),10+group)
            self.assertEqual(struct.unpack_from('>i',first[0].payload)[0],-1)
            quoted=session.handle(Event(0x202,kind=qkind),20+group)
            self.assertEqual(struct.unpack_from('>iQ',quoted[0].payload),(0,ED_COSTS[group][0]))
            result=session.handle(Event(0x202,kind=ekind),30+group)
            self.assertEqual(struct.unpack_from('>I',result[0].payload,12)[0],1)
            retry=session.handle(Event(0x202,kind=ekind),30+group)
            self.assertEqual(struct.unpack_from('>I',retry[0].payload,12)[0],0)
        self.deposit(self.gear)
        events=session.handle(Event(0x202,kind=0x54f),60)
        self.assertEqual([e.kind for e in events],[0x105,0x550])
        self.assertEqual(struct.unpack_from('>iI',events[1].payload),(0,1))
        self.assertEqual(struct.unpack_from('>i',session.handle(Event(0x202,kind=0x54b,payload=b'x'),61)[0].payload)[0],-1)


if __name__=='__main__':unittest.main()
