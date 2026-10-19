"""Money conservation and immediate bank products in disposable account saves."""
import sqlite3,struct,unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from els_server.storage.bank_money import transfer,balance
from els_server.storage.bank_state import snapshot,contents,quote,expand
from els_server.storage.shop_state import catalog,purchase
from els_server.domain.bank_memberships import PRODUCTS,offers
from els_server.domain.local_session import LocalSession,LocalAccount
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event
from els_server.domain.bank_rules import TIERS,ED_LIMITS,player_ed_limit
from els_server.protocol.bank_messages import money_request


def money_wire(deposit,amount):return struct.pack('>BQ',deposit,amount)
def shop_wire(template,count=1):return struct.pack('>IIH',1,1200000000+template,count)


class BankMoneyMembershipTests(unittest.TestCase):
    setUp=fixture.SaleTests.setUp
    grant=fixture.SaleTests.grant
    items=fixture.SaleTests.items
    dump=fixture.SaleTests.dump
    money=fixture.SaleTests.money

    def fund(self,amount=1_000_000_000,level=99):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE reward_balances SET ed=? WHERE uid=1001',(amount,))
            db.execute('UPDATE characters SET level=?',(level,))

    def bank(self,owner=1001):
        with closing(sqlite3.connect(self.path)) as db:return balance(db,owner)[0]

    def session(self):
        result=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,gate_test=True,
            population_test=True,clear_test=True,reward_test=True,item_test=True,shop_test=True,client_build='dx11_260923')
        result.role='game';result.phase='town_ready';return result

    def test_cross_character_deposit_withdraw_preserves_total_and_survives_restart(self):
        self.fund();before=self.money()
        result=transfer(self.path,1001,money_wire(True,500_000_000),'deposit')
        self.assertEqual(struct.unpack('>iBQQ',result),(0,1,500_000_000,500_000_000))
        result=transfer(self.path,self.other,money_wire(False,300_000_000),'withdraw')
        self.assertEqual(struct.unpack('>iBQQ',result),(0,0,200_000_000,300_000_000))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(sum(r[0] for r in db.execute('SELECT ed FROM reward_balances'))+self.bank(),before)
        account=LocalAccount(LocalState(self.path));account.enable_characters()
        self.assertEqual(self.bank(account.for_character(self.other).uid),200_000_000)
        self.assertEqual(struct.unpack_from('>Q',contents(self.path,self.other,16)[-1].payload,8)[0],200_000_000)

    def test_retry_uses_current_absolute_balances_without_repeated_transfer(self):
        self.fund();p=money_wire(True,100)
        transfer(self.path,1001,p,'once');transfer(self.path,1001,money_wire(True,200),'second')
        before=self.dump();wire=transfer(self.path,1001,p,'once')
        self.assertEqual(self.dump(),before);self.assertEqual(struct.unpack('>iBQQ',wire),(0,1,300,999_999_700))
        with self.assertRaises(ValueError):transfer(self.path,1001,money_wire(False,100),'once')

    def test_concurrent_withdrawals_and_repeated_deposit_conserve_money(self):
        self.fund(1000)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:transfer(self.path,1001,money_wire(True,1000),'same'),range(2)))
        self.assertEqual(self.money(),0);self.assertEqual(self.bank(),1000)
        def take(owner):
            try:transfer(self.path,owner,money_wire(False,1000),'take-'+str(owner));return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(take,(1001,self.other))),1)
        self.assertEqual(self.bank(),0)
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(sum(r[0] for r in db.execute('SELECT ed FROM reward_balances')),1000)

    def test_bank_tier_limits_and_level_wallet_limit_use_original_data(self):
        self.assertEqual((player_ed_limit(1),player_ed_limit(99)),(500_000,70_000_000_000))
        self.fund(8_000_000_000)
        transfer(self.path,1001,money_wire(True,7_000_000_000),'full')
        before=self.dump()
        with self.assertRaises(ValueError):transfer(self.path,1001,money_wire(True,1),'over')
        self.assertEqual(self.dump(),before)
        purchase(self.path,shop_wire(283132),'expand')
        transfer(self.path,1001,money_wire(True,100),'after-expand')
        self.assertEqual(self.bank(),7_000_000_100)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE characters SET level=1 WHERE uid=?',(self.other,))
        transfer(self.path,self.other,money_wire(False,500_000),'level-one-full');before=self.dump()
        with self.assertRaises(ValueError):transfer(self.path,self.other,money_wire(False,1),'level-one-over')
        self.assertEqual(self.dump(),before)

    def test_money_account_isolation_negative_zero_bool_trailing_and_encoder_rollback(self):
        self.fund(1000);transfer(self.path,1001,money_wire(True,500),'own')
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE character_owners SET account_id=2 WHERE uid=?',(self.other,))
        self.assertEqual(self.bank(self.other),0)
        before=self.dump()
        for owner,p in ((self.other,money_wire(False,1)),(1001,money_wire(True,501)),(1001,money_wire(False,501))):
            with self.assertRaises(ValueError):transfer(self.path,owner,p,'bad')
            self.assertEqual(self.dump(),before)
        for p in (b'',money_wire(True,0),money_wire(True,70_000_000_001),b'\2'+bytes(8),money_wire(True,1)+b'x',money_wire(True,1)[:-1],b'\1'+b'\xff'*8):
            with self.assertRaises(ValueError):money_request(p)
        with patch('els_server.storage.bank_money.money_ack',side_effect=ValueError('encode')):
            with self.assertRaises(ValueError):transfer(self.path,1001,money_wire(True,1),'encode')
        self.assertEqual(self.dump(),before)

    def test_all_ten_memberships_apply_immediately_without_inventory_delivery(self):
        self.fund();original=self.items();spent=0
        offered={p['template']:p for p in offers()}
        for t,(group,before,after) in PRODUCTS.items():
            if t==283131:continue
            wire=purchase(self.path,shop_wire(t),'member-'+str(t));spent+=offered[t]['price']
            self.assertEqual(struct.unpack_from('>iiI',wire),(0,0,0))
            self.assertEqual(snapshot(self.path,1001)['bank_capacities'][group],after)
            self.assertEqual(self.items(),original)
        self.assertEqual(self.money(),1_000_000_000-spent)
        self.assertEqual(snapshot(self.path,self.other)['bank_capacities'],{8:8,16:48})
        before=self.dump()
        with self.assertRaises(ValueError):purchase(self.path,shop_wire(283136),'already-max')
        self.assertEqual(self.dump(),before)

    def test_credit_guarantee_normal_to_48_only_and_shared_across_characters(self):
        self.fund();price=next(p['price'] for p in offers() if p['template']==283131)
        purchase(self.path,shop_wire(283131),'credit')
        self.assertEqual(snapshot(self.path,self.other)['bank_capacities'][16],48)
        self.assertEqual(self.money(),1_000_000_000-price)
        before=self.dump();purchase(self.path,shop_wire(283131),'credit');self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):purchase(self.path,shop_wire(283131),'credit-again')

    def test_membership_wrong_tier_bulk_and_duplicate_bank_cart_rejected_atomically(self):
        self.fund();before=self.dump()
        bad=[shop_wire(213470),shop_wire(213460,2),struct.pack('>IIHIH',2,1200213460,1,1200213470,1)]
        for p in bad:
            with self.assertRaises(ValueError):purchase(self.path,p,'bad')
            self.assertEqual(self.dump(),before)
        with patch('els_server.storage.shop_state.ed_purchase_ack',side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):purchase(self.path,shop_wire(213460),'encode')
        self.assertEqual(self.dump(),before)

    def test_membership_retry_no_stale_ed_and_concurrent_buy_debits_once(self):
        self.fund();p=shop_wire(213460)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:purchase(self.path,p,'same-member'),range(2)))
        purchase(self.path,shop_wire(283132),'another')
        before=self.dump();reply=purchase(self.path,p,'same-member')
        self.assertEqual(self.dump(),before);self.assertEqual(struct.unpack_from('>Q',reply,12)[0],self.money())
        self.assertEqual(self.money(),988_000_000)

    def test_native_session_membership_notice_replay_and_bank_money_phase_guard(self):
        self.fund();s=self.session();s.handle(Event(0x202,kind=0x80d,payload=struct.pack('>i',1)),1)
        result=s.handle(Event(0x202,kind=0x80f,payload=shop_wire(213460)),2)
        self.assertEqual([e.kind for e in result],[0x810,0x26c])
        self.assertEqual(struct.unpack('>Iii',result[1].payload[:12]),(1,8,8))
        self.assertEqual([e.kind for e in s.handle(Event(0x202,kind=0x80f,payload=shop_wire(213460)),2)],[0x810])
        result=s.handle(Event(0x202,kind=0x7d7,payload=money_wire(True,100)),3)
        self.assertEqual(struct.unpack('>iBQQ',result[0].payload),(0,1,100,self.money()))
        s.phase='dungeon_active';before=self.dump()
        result=s.handle(Event(0x202,kind=0x7d7,payload=money_wire(False,100)),4)
        self.assertEqual(struct.unpack_from('>i',result[0].payload)[0],-1);self.assertEqual(self.dump(),before)

    def test_mixed_bank_cart_retry_refreshes_replacement_instead_of_old_item(self):
        from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
        from els_server.storage.bank_state import transfer as move
        from tests.test_bank_state import payload as move_payload
        self.fund();s=self.session();s.ed_catalog_loaded=True
        physical=[p for p in catalog(1) if p['category']//10==2 and TEMPLATE_BAG_GROUPS.get(p['template'])==27][:2]
        p=struct.pack('>IIHIH',2,1200213460,1,physical[0]['sku'],1)
        original={i['uid'] for i in self.items()}
        result=s.handle(Event(0x202,kind=0x80f,payload=p),101)
        self.assertEqual([e.kind for e in result],[0x810,0x26c])
        item=next(i for i in self.items() if i['uid'] not in original)
        move(self.path,1001,move_payload((item['group'],item['slot']),(16,0),item),'move-purchased')
        replacement=self.grant(physical[1]['template']);self.assertEqual(replacement['slot'],item['slot'])
        before=self.dump();again=s.handle(Event(0x202,kind=0x80f,payload=p),101)
        self.assertEqual(self.dump(),before);self.assertEqual([e.kind for e in again],[0x810,0x105])
        self.assertEqual(struct.unpack_from('>I',again[0].payload,8)[0],0)
        self.assertEqual(struct.unpack_from('>Q',again[1].payload,4)[0],replacement['uid'])


if __name__=='__main__':unittest.main()
