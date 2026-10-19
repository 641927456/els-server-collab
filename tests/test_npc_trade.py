"""Original stock purchases/buyback with temporary saves and hostile requests."""
import json,sqlite3,struct
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from els_server.domain.fashion_state import record
from els_server.domain.npc_trade import offer
from els_server.protocol.npc_trade_messages import purchase_request,repurchase_request
from els_server.protocol.protocol_codec import Event
from els_server.domain.local_session import LocalSession
from els_server.storage.npc_sale import sell
from els_server.storage.npc_trade import purchase,repurchase,history
sale_payload=fixture.payload


def buy_payload(entries=((11006011,1),),merchant=10011):
    return struct.pack('>BHI',0,0,len(entries))+b''.join(struct.pack('>ii',*e) for e in entries)+struct.pack('>i',merchant)


def back_payload(item,index=0,merchant=10011):
    return struct.pack('>i',index)+record(item)+struct.pack('>i',merchant)


class TradeTests(fixture.SaleTests):
    # Inherit the fixture helpers, not SaleTests' test methods (see below).
    def history(self,session='local'):
        with closing(sqlite3.connect(self.path)) as db,db:return history(db,1001,session)

    def fund(self,amount=1000000):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=? WHERE uid=1001',(amount,))

    def test_purchase_original_offer_money_and_relogin(self):
        self.fund();before=self.money()
        e=purchase(self.path,1001,20002,buy_payload(), 'buy')
        self.assertEqual(e[0].kind,0xeb);self.assertEqual(self.money(),before-7200)
        item=next(i for i in self.items() if i['template']==11006011)
        self.assertEqual(item['durability'],10000)
        self.assertEqual(self.items(),fixture.LocalAccount(fixture.LocalState(self.path)).get_inventory_snapshot()['items'])

    def test_purchase_stock_town_currency_and_quantity_rejected(self):
        self.fund()
        for town,p in ((20000,buy_payload()),(20002,buy_payload(merchant=10000)),
                (20002,buy_payload(((60100,1),))), (20002,buy_payload(((11006011,0),))),
                (20002,buy_payload(((11006011,1),(11006011,2))))):
            before=self.dump()
            with self.assertRaises(ValueError):purchase(self.path,1001,town,p,'bad')
            self.assertEqual(self.dump(),before)
        # Mixed ED/VP offerings cannot become ED-only purchases.
        with self.assertRaises(ValueError):offer(20010,10024,700275)

    def test_purchase_insufficient_money_and_bag_full_roll_back(self):
        self.fund(0);before=self.dump()
        with self.assertRaises(ValueError):purchase(self.path,1001,20002,buy_payload(),'poor')
        self.assertEqual(self.dump(),before)
        self.fund()
        with patch('els_server.storage.bag_capacity.allowances',return_value={1:0}):
            before=self.dump()
            with self.assertRaises(ValueError):purchase(self.path,1001,20002,buy_payload(),'full')
            self.assertEqual(self.dump(),before)

    def test_purchase_retry_returns_current_slots_and_charges_once(self):
        self.fund();p=buy_payload();purchase(self.path,1001,20002,p,'once')
        before=self.dump();ed=self.money()
        events=purchase(self.path,1001,20002,p,'once')
        self.assertEqual(struct.unpack('>iQiI',events[0].payload),(0,ed,0,0))
        self.assertEqual(events[1].kind,0x105);self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):purchase(self.path,1001,20002,buy_payload(((11006011,2),)),'once')

    def test_buyback_preserves_full_instance_not_new_acquisition(self):
        from els_server.storage.equipment_attributes import replace_attributes
        from els_server.storage.equipment_durability import replace_durability
        from els_server.storage.equipment_enhancement import replace
        from els_server.storage.item_expiration import assign
        self.fund()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');replace_attributes(db,1001,self.gear['uid'],[0]*4,[1,0,0,0])
            replace_durability(db,1001,self.gear['uid'],10000,5000)
            replace(db,1001,self.gear['uid'],0,3);assign(db,1001,self.gear['uid'],2200000000)
        item=next(i for i in self.items() if i['uid']==self.gear['uid'])
        sell(self.path,1001,sale_payload([(item['uid'],1)]),'sell')
        before=self.money();events=repurchase(self.path,1001,back_payload(item),'back')
        self.assertEqual(events[0].kind,0x568);self.assertEqual(self.money(),before-117600)
        restored=next(i for i in self.items() if i['uid']==item['uid'])
        self.assertEqual(restored,item);self.assertEqual(self.history(),[])
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_buyback_merges_the_existing_stack_and_updates_history_count(self):
        self.fund();item=self.grant(701000,20)
        sell(self.path,1001,sale_payload([(item['uid'],7)]),'sell')
        sold=dict(item,count=3);repurchase(self.path,1001,back_payload(sold),'back')
        self.assertEqual(self.history()[0][1]['count'],4)
        stacks=[i for i in self.items() if i['template']==701000]
        self.assertEqual([i['count'] for i in stacks],[16]);self.assertEqual(stacks[0]['uid'],item['uid'])

    def test_buyback_merges_in_full_bag_and_rolls_back_partial_overflow(self):
        self.fund();item=self.grant(701000,20)
        sell(self.path,1001,sale_payload([(item['uid'],7)]),'sell')
        limits={g:1 for g in (1,2,3,4,5,6,7,21,27,11)}
        with patch('els_server.storage.bag_capacity.allowances',return_value=limits):
            repurchase(self.path,1001,back_payload(dict(item,count=3)),'merge-in-full-bag')
        # Simulate later gathering up to this material's 10,000-item limit.
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE inventory_items SET count=9999 WHERE uid=?',(item['uid'],))
        before=self.dump()
        with patch('els_server.storage.bag_capacity.allowances',return_value=limits):
            with self.assertRaises(ValueError):repurchase(self.path,1001,back_payload(dict(item,count=4)),'needs-second-slot')
        self.assertEqual(self.dump(),before)
        repurchase(self.path,1001,back_payload(dict(item,count=4)),'needs-second-slot')
        self.assertEqual(sorted(i['count'] for i in self.items() if i['template']==701000),[3,10000])

    def test_buyback_forgery_owner_session_and_stale_index_rollback(self):
        self.fund();sell(self.path,1001,sale_payload([(self.gear['uid'],1)]),'sell')
        for item,index,owner,session in ((dict(self.gear,template=30160),0,1001,'local'),
                (dict(self.gear,enhancement=20),0,1001,'local'),(self.gear,1,1001,'local'),
                (self.gear,0,self.other,'local'),(self.gear,0,1001,'other-session')):
            before=self.dump()
            with self.assertRaises(ValueError):repurchase(self.path,owner,back_payload(item,index),'bad',session)
            self.assertEqual(self.dump(),before)

    def test_buyback_retry_does_not_remove_next_history_or_charge_again(self):
        self.fund();second=self.grant(30160)
        sell(self.path,1001,sale_payload([(self.gear['uid'],1),(second['uid'],1)]),'sell')
        p=back_payload(self.gear);repurchase(self.path,1001,p,'back');before=self.dump()
        events=repurchase(self.path,1001,p,'back')
        self.assertEqual(struct.unpack_from('>i',events[0].payload)[0],-1)
        self.assertEqual(self.history()[0][1]['uid'],second['uid']);self.assertEqual(self.dump(),before)

    def test_buyback_eight_history_entries_match_native_eviction(self):
        items=[self.grant(60100) for _ in range(10)]
        sell(self.path,1001,sale_payload([(i['uid'],1) for i in items]),'sell')
        self.assertEqual([i['uid'] for k,i in self.history()],[i['uid'] for i in items[-8:]])
        before=self.dump();sell(self.path,1001,sale_payload([(i['uid'],1) for i in items]),'sell')
        self.assertEqual(self.dump(),before)

    def test_buyback_encoder_failure_and_insufficient_money_are_atomic(self):
        self.fund();sell(self.path,1001,sale_payload([(self.gear['uid'],1)]),'sell')
        before=self.dump()
        with patch('els_server.storage.npc_trade.repurchase_ack',side_effect=ValueError('encode')):
            with self.assertRaises(ValueError):repurchase(self.path,1001,back_payload(self.gear),'back')
        self.assertEqual(self.dump(),before)
        self.fund(0);before=self.dump()
        with self.assertRaises(ValueError):repurchase(self.path,1001,back_payload(self.gear),'poor')
        self.assertEqual(self.dump(),before)

    def test_buyback_respects_bank_uid_reservations_and_current_town(self):
        from els_server.storage.bank_state import transfer,snapshot
        self.fund();item=self.grant(701000,10)
        sell(self.path,1001,sale_payload([(item['uid'],10)]),'sell')
        before=self.dump()
        with self.assertRaises(ValueError):repurchase(self.path,1001,back_payload(dict(item,count=3)),'wrong-town',town=20000)
        self.assertEqual(self.dump(),before)
        repurchase(self.path,1001,back_payload(dict(item,count=3)),'back-1',town=20002)
        restored=next(i for i in self.items() if i['template']==701000)
        transfer(self.path,1001,struct.pack('>BiBiiQi',restored['group'],restored['slot'],8,0,3,0,701000),'bank')
        repurchase(self.path,1001,back_payload(dict(item,count=7)),'back-2',town=20002)
        bank=snapshot(self.path,1001)['bank_items'][0]['item']
        bag=next(i for i in self.items() if i['template']==701000)
        self.assertNotEqual(bank['uid'],bag['uid']);self.assertEqual(bank['count']+bag['count'],10)

    def test_concurrent_purchase_and_buyback_retries_commit_once(self):
        self.fund()
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _:purchase(self.path,1001,20002,buy_payload(),'parallel'),range(2)))
        self.assertEqual(self.money(),1000000-7200)
        sell(self.path,1001,sale_payload([(self.gear['uid'],1)]),'sell');before=self.money()
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _:repurchase(self.path,1001,back_payload(self.gear),'parallel-back'),range(2)))
        self.assertEqual(self.money(),before-117600);self.assertEqual(self.history(),[])

    def test_trade_dispatch_rejects_non_town_and_missing_sequence(self):
        self.fund();session=LocalSession(self.account,client_build='dx11_260923',item_test=True,reward_test=True,clear_test=True,population_test=True,gate_test=True,npc_slot_test=True,enter_town=True,enter_dungeon=True)
        session.role='game';session.phase='dungeon_active'
        for kind,p in ((0xea,buy_payload()),(0x567,back_payload(self.gear))):
            before=self.dump();answer=session.handle(Event(0x202,kind=kind,payload=p),1)
            self.assertEqual(answer[0].kind,kind+1);self.assertEqual(struct.unpack_from('>i',answer[0].payload)[0],-1)
            self.assertEqual(self.dump(),before)

    def test_town_session_purchase_sale_buyback_bank_and_character_reload(self):
        from els_server.storage.bank_state import snapshot as bank_snapshot
        from els_server.storage.local_state import TOWN_SCENES
        self.fund();self.account.location={**self.account.get_location(),'map':20002,'scene':TOWN_SCENES[20002]}
        args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        session=LocalSession(self.account,**args);session.role='game';session.phase='town_ready'
        bought=session.handle(Event(0x202,kind=0xea,payload=buy_payload()),1)
        self.assertEqual(struct.unpack_from('>i',bought[0].payload)[0],0)
        item=next(i for i in self.items() if i['template']==11006011)
        sale=session.handle(Event(0x202,kind=0xec,payload=sale_payload([(item['uid'],1)],merchant=10011)),2)
        self.assertEqual(struct.unpack_from('>i',sale[0].payload)[0],0)
        bought_back=session.handle(Event(0x202,kind=0x567,payload=back_payload(item)),3)
        self.assertEqual(struct.unpack_from('>i',bought_back[0].payload)[0],0)
        bank=session.handle(Event(0x202,kind=0x551,payload=struct.pack('>BiBiiQi',1,item['slot'],8,0,1,0,item['template'])),4)
        self.assertEqual(struct.unpack_from('>i',bank[0].payload,len(bank[0].payload)-4)[0],0)
        self.assertEqual(bank_snapshot(self.path,1001)['bank_items'][0]['item']['uid'],item['uid'])
        original_history=session.npc_history_id;session.phase='channels_ready'
        init=session.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1001)),5)
        self.assertIn(0x2a,[e.kind for e in init]);self.assertNotEqual(session.npc_history_id,original_history)
        self.assertEqual(self.account.character()['bank_items'][0]['item']['uid'],item['uid'])


# Use SaleTests only as a fixture provider; do not run inherited cases twice.
for _name in list(vars(fixture.SaleTests)):
    if _name.startswith('test_') and _name not in vars(TradeTests):setattr(TradeTests,_name,None)
