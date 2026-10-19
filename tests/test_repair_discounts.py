import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.equipment_durability import replace_durability
from els_server.storage.equipment_repair import repair
from els_server.domain.repair_pricing import multiplier,character_quote,catalog
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,FASHION_EQUIP_SLOTS
from els_server.domain.fashion_state import move_fashion


class RepairDiscountTests(unittest.TestCase):
    def test_registered_discount_templates_share_verified_effect_and_slot(self):
        definitions=catalog()['template_effects'];registered={int(k):v for k,v in definitions.items() if int(k) in VERIFIED_TEMPLATES}
        # Later catalog additions also expose native discount accessories.
        self.assertGreaterEqual(len(registered),39)
        for template,effects in registered.items():
            self.assertEqual(effects,[5211])
            if template in FASHION_EQUIP_SLOTS:self.assertEqual(FASHION_EQUIP_SLOTS[template],51)
            item=dict(uid=1,template=template,group=9,slot=FASHION_EQUIP_SLOTS.get(template,0))
            self.assertEqual(multiplier(dict(unit_type=1),[item])['multiplier'],0.8999999761581421)
            self.assertEqual(multiplier(dict(unit_type=1),[dict(item,group=7)])['multiplier'],1.)

    def test_float32_sum_cap_and_final_truncation(self):
        # Mathematical boundary coverage: not a claim that seven same-slot items
        # can be equipped. Inventory validation independently rejects that layout.
        c=dict(unit_type=1)
        sources=[dict(uid=n+1,template=208170,group=9,slot=n) for n in range(8)]
        self.assertEqual(multiplier(c,sources[:6])['multiplier'],0.3999999761581421)
        self.assertEqual(multiplier(c,sources[:7])['multiplier'],0.30000001192092896)
        self.assertEqual(multiplier(c,sources)['multiplier'],0.30000001192092896)
        gear=dict(uid=20,template=60100,metadata=1,count=1,group=1,slot=0,durability=9999)
        q=character_quote([gear],c,[gear,sources[0]])
        self.assertEqual(q['subtotal_ed'],8);self.assertEqual(q['total_ed'],7)

    def test_owned_equipment_controls_payment_and_unwear_restores_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'save.sqlite3';account=LocalAccount(LocalState(p));account.enable_characters()
            with closing(sqlite3.connect(p)) as db,db:
                gear,accessory=grant_items(db,[dict(template=60100,metadata=1,quantity=1,group=1),dict(template=208170,metadata=0,quantity=1,group=7)])
                replace_durability(db,1001,gear['uid'],10000,0)
                db.execute('UPDATE reward_balances SET ed=73799 WHERE uid=1001')
            move_fashion(p,struct.pack('>BiBiB',7,accessory['slot'],9,51,0))
            req=struct.pack('>IQBBi',1,gear['uid'],0,0,0);before=account.get_inventory_snapshot()
            with self.assertRaises(ValueError):repair(p,1001,req,'poor')
            self.assertEqual(account.get_inventory_snapshot(),before)
            with closing(sqlite3.connect(p)) as db,db:db.execute('UPDATE reward_balances SET ed=73800 WHERE uid=1001')
            before=account.get_inventory_snapshot()
            with patch('els_server.storage.equipment_repair.acknowledgement',side_effect=RuntimeError('codec')):
                with self.assertRaises(RuntimeError):repair(p,1001,req,'paid')
            self.assertEqual(account.get_inventory_snapshot(),before)
            paid=repair(p,1001,req,'paid');self.assertEqual(paid['balances']['ed'],0);self.assertEqual(paid['evidence']['ed_cost'],73800)
            self.assertEqual(paid['evidence']['quote']['pricing_context']['sources'][0]['uid'],accessory['uid'])
            move_fashion(p,struct.pack('>BiBiB',9,51,7,accessory['slot'],0))
            with closing(sqlite3.connect(p)) as db,db:
                db.execute('BEGIN IMMEDIATE');replace_durability(db,1001,gear['uid'],10000,0)
                db.execute('UPDATE reward_balances SET ed=82000 WHERE uid=1001')
            replay=repair(p,1001,req,'paid');self.assertTrue(replay['replayed']);self.assertEqual(replay['balances']['ed'],82000)
            paid=repair(p,1001,req,'unworn');self.assertEqual(paid['evidence']['ed_cost'],82000)
            self.assertEqual(paid['balances']['ed'],0)


if __name__=='__main__':unittest.main()
