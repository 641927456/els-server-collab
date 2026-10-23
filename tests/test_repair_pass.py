import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from tests.historical_inventory import seed_existing_items as grant_items
from els_server.storage.equipment_durability import replace_durability
from els_server.storage.equipment_repair import repair
from els_server.storage.item_expiration import remove_due
from els_server.domain.repair_pricing import multiplier


REPAIR_ACCOUNT_ID=1  # Explicit owner for this temporary database fixture.


class RepairPassTests(unittest.TestCase):
    def test_explicit_timed_grant_and_free_repair_atomicity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'save.db';a=LocalAccount(LocalState(path),account_id=REPAIR_ACCOUNT_ID);a.enable_characters();deadline=1792053000
            plan=dict(template=711611,metadata=0,quantity=1,group=4)
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('BEGIN IMMEDIATE')
                with self.assertRaises(ValueError):grant_items(db,[plan])
                with self.assertRaises(ValueError):grant_items(db,[dict(plan,quantity=2,expires_at=deadline)])
                gear,coupon=grant_items(db,[dict(template=60100,metadata=1,quantity=1,group=1),dict(plan,expires_at=deadline)])
                replace_durability(db,1001,gear['uid'],10000,0)
                db.execute('UPDATE reward_balances SET ed=0 WHERE uid=1001')
            req=struct.pack('>IQBBi',1,gear['uid'],0,0,0);before=a.get_inventory_snapshot()
            with patch('time.time',return_value=deadline):
                with patch('els_server.storage.equipment_repair.acknowledgement',side_effect=RuntimeError('encoder')):
                    with self.assertRaises(RuntimeError):repair(path,1001,req,'free',account_id=REPAIR_ACCOUNT_ID)
                self.assertEqual(a.get_inventory_snapshot(),before)
                answer=repair(path,1001,req,'free',account_id=REPAIR_ACCOUNT_ID)
                self.assertEqual(answer['evidence']['ed_cost'],0)
                self.assertEqual(answer['evidence']['quote']['pricing_context']['free_pass_uids'],[coupon['uid']])
                self.assertEqual(answer['balances']['ed'],0)
                self.assertEqual(answer['inventory'][0]['durability'],10000)
                self.assertEqual(next(i for i in answer['inventory'] if i['uid']==coupon['uid']),coupon)
                self.assertTrue(repair(path,1001,req,'free',account_id=REPAIR_ACCOUNT_ID)['replayed'])
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('BEGIN IMMEDIATE');replace_durability(db,1001,gear['uid'],10000,0)
            before=a.get_inventory_snapshot()
            with patch('time.time',return_value=deadline+1):
                with self.assertRaises(ValueError):repair(path,1001,req,'expired-without-sweep',account_id=REPAIR_ACCOUNT_ID)
            self.assertEqual(a.get_inventory_snapshot(),before)
            self.assertEqual(len(remove_due(path,1001,now=deadline+1)),1)
            with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=82000 WHERE uid=1001')
            with patch('time.time',return_value=deadline+1):
                paid=repair(path,1001,req,'paid-after-expiry',account_id=REPAIR_ACCOUNT_ID)
            self.assertEqual(paid['evidence']['ed_cost'],82000);self.assertEqual(paid['balances']['ed'],0)
            reopened=LocalAccount(LocalState(path),account_id=REPAIR_ACCOUNT_ID);reopened.enable_characters()
            self.assertEqual(reopened.get_inventory_snapshot(),a.get_inventory_snapshot())

    def test_pass_scope_and_expired_discount(self):
        deadline=1792053000;coupon=dict(uid=12,template=711611,group=4,slot=0,count=1,expires_at=deadline)
        accessory=dict(uid=13,template=208170,group=9,slot=51,expires_at=deadline)
        with patch('time.time',return_value=deadline):
            self.assertEqual(multiplier(dict(unit_type=1),[coupon,accessory])['multiplier'],0.)
            for group in (8,13,14,16):self.assertEqual(multiplier(dict(unit_type=1),[dict(coupon,group=group)])['multiplier'],1.)
        with patch('time.time',return_value=deadline+1):
            self.assertEqual(multiplier(dict(unit_type=1),[coupon,accessory])['multiplier'],1.)
        with self.assertRaises(ValueError):multiplier(dict(unit_type=1),[{k:v for k,v in coupon.items() if k!='expires_at'}])

    def test_pass_does_not_authorize_other_character_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'save.db';a=LocalAccount(LocalState(path),account_id=REPAIR_ACCOUNT_ID);a.enable_characters()
            other=a.characters.create('PassOther',5,'pass-other')['uid'];a.for_character(other)
            deadline=1792053000
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('BEGIN IMMEDIATE')
                grant_items(db,[dict(template=711611,metadata=0,group=4,quantity=1,expires_at=deadline)],1001)
                gear=grant_items(db,[dict(template=100,metadata=1,group=1,quantity=1)],other)[0]
                replace_durability(db,other,gear['uid'],10000,0)
                db.execute('UPDATE reward_balances SET ed=0 WHERE uid=?',(other,))
            req=struct.pack('>IQBBi',1,gear['uid'],0,0,0)
            with patch('time.time',return_value=deadline):
                with self.assertRaises(ValueError):repair(path,other,req,'other-poor',account_id=REPAIR_ACCOUNT_ID)
                with self.assertRaises(ValueError):repair(path,1001,req,'foreign-gear',account_id=REPAIR_ACCOUNT_ID)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(load_items(db,other)[0]['durability'],0)
                self.assertEqual(load_items(db,1001)[0]['count'],1)


if __name__=='__main__':unittest.main()
