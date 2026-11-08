"""Exercise automatic material selection and its existing SQL boundaries."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import struct
import sys
import unittest
import bootstrap
from test_item_contracts import OwnedFixture,NOW
from els_server.storage import (attribute_enchant,consumables,ariel_attendance,
    equipment_repair,item_locks,quick_slots)
from els_server.domain.quick_bindings import item_binding


class MaterialSelection(unittest.TestCase):
    def fixture(self):
        fixture=OwnedFixture();self.addCleanup(fixture.close);return fixture

    def test_enchant_skips_locked_crystals_and_uses_unlocked_stack(self):
        f=self.fixture();weapon=f.add(30154);locked=f.add(130048,6,lock=NOW+3600);available=f.add(130048,6)
        result=attribute_enchant.change_attribute(f.path,1001,struct.pack('>QBB',weapon['uid'],0,1),'owned-enchant')
        self.assertEqual(result['evidence']['materials'],[dict(uid=available['uid'],template=130048,quantity=6)])
        with closing(sqlite3.connect(f.path)) as db:
            self.assertEqual(db.execute('SELECT count FROM inventory_items WHERE uid=?',(locked['uid'],)).fetchone(),(6,))
            self.assertIsNone(db.execute('SELECT count FROM inventory_items WHERE uid=?',(available['uid'],)).fetchone())
        before=f.dump();self.assertTrue(attribute_enchant.change_attribute(f.path,1001,struct.pack('>QBB',weapon['uid'],0,1),'owned-enchant')['replayed']);self.assertEqual(f.dump(),before)

    def test_only_locked_crystals_reject_without_charge(self):
        f=self.fixture();weapon=f.add(30154);f.add(130048,6,lock=NOW+3600);before=f.dump()
        with self.assertRaises(ValueError):attribute_enchant.change_attribute(f.path,1001,struct.pack('>QBB',weapon['uid'],0,1),'owned-locked')
        self.assertEqual(f.dump(),before)

    def test_repair_and_enchant_reject_deleted_actor(self):
        for finalized in (False,True):
            f=self.fixture();weapon=f.add(30154);f.add(130048,6);f.lifecycle(finalized)
            actions=(lambda:attribute_enchant.change_attribute(f.path,1001,struct.pack('>QBB',weapon['uid'],0,1),'owned-retired-enchant'),
                     lambda:equipment_repair.repair(f.path,1001,struct.pack('>IQ',1,weapon['uid'])+bytes(6),'owned-retired-repair',account_id=1))
            for action in actions:
                before=f.dump()
                with self.assertRaisesRegex(ValueError,'pending deletion or finalized'):action()
                self.assertEqual(f.dump(),before)

    def test_unknown_enchant_character_retains_native_failure_code(self):
        from els_server.protocol.enchant_messages import EnchantRejected,EnchantResult
        f=self.fixture();weapon=f.add(30154);before=f.dump()
        with self.assertRaises(EnchantRejected) as failure:
            attribute_enchant.change_attribute(f.path,9999,struct.pack('>QBB',weapon['uid'],0,1),'owned-unknown')
        self.assertEqual(failure.exception.result,EnchantResult.UNKNOWN_CHARACTER)
        self.assertEqual(f.dump(),before)

    def potion_setup(self,f,*,unlocked):
        locked=f.add(77000,2,lock=NOW+3600)
        available=f.add(77000,2) if unlocked else None
        values=quick_slots.empty();values[0]=item_binding(77000)
        quick_slots.save_request(f.path,struct.pack('>i',1)+quick_slots.encode(values),1001)
        return locked,available

    def test_shortcut_uses_unlocked_potion_stack(self):
        f=self.fixture();locked,available=self.potion_setup(f,unlocked=True)
        result=consumables.use(f.path,1001,bytes(5),'owned-potion',now=NOW,account_id=1)
        self.assertEqual([e.kind for e in result],[0x114,0x115])
        with closing(sqlite3.connect(f.path)) as db:
            self.assertEqual(db.execute('SELECT count FROM inventory_items WHERE uid=?',(locked['uid'],)).fetchone(),(2,))
            self.assertEqual(db.execute('SELECT count FROM inventory_items WHERE uid=?',(available['uid'],)).fetchone(),(1,))
        before=f.dump();consumables.use(f.path,1001,bytes(5),'owned-potion',now=NOW+1,account_id=1);self.assertEqual(f.dump(),before)

    def test_locked_potions_reject_without_cooldown_or_consumption(self):
        f=self.fixture();self.potion_setup(f,unlocked=False);before=f.dump()
        with self.assertRaises(ValueError):consumables.use(f.path,1001,bytes(5),'owned-locked-potion',now=NOW,account_id=1)
        self.assertEqual(f.dump(),before)

    def makeup_setup(self,f):
        with closing(sqlite3.connect(f.path)) as db,db:
            db.execute('BEGIN');ariel_attendance.initialize(db)
            db.execute('INSERT INTO ariel_attendance_periods VALUES(?,1,?,?,0,NULL,1)',('owned-period',NOW-2*86400,NOW-2*86400+ariel_attendance.DURATION))

    def makeup(self,f):
        from els_server.protocol import ariel_attendance_messages as wire
        def encode(db,result,state,balance):
            return [wire.acknowledgement(0xc90),*wire.inventory(result['items'],result['changed']),wire.status(state)]
        return ariel_attendance.perform(f.path,1,1001,'00000000-0000-4000-8000-000000000001',1,0xc90,struct.pack('>i',3),None,
            validate=lambda:None,encode=encode,now=lambda:NOW)

    def test_makeup_selects_unlocked_coupon_when_earliest_is_locked(self):
        f=self.fixture();self.makeup_setup(f)
        locked=f.add(721051,lock=NOW+3600,expiry=NOW+7200)
        available=f.add(721051,expiry=NOW+14400)
        self.makeup(f)
        with closing(sqlite3.connect(f.path)) as db:
            self.assertEqual(db.execute('SELECT count FROM inventory_items WHERE uid=?',(locked['uid'],)).fetchone(),(1,))
            self.assertIsNone(db.execute('SELECT count FROM inventory_items WHERE uid=?',(available['uid'],)).fetchone())
            self.assertEqual(db.execute('SELECT attended FROM ariel_attendance_periods').fetchone(),(1,))
        before=f.dump();self.makeup(f);self.assertEqual(f.dump(),before)

    def test_makeup_consumes_elapsed_lock_without_foreign_key_failure(self):
        f=self.fixture();self.makeup_setup(f);coupon=f.add(721051,lock=NOW-1)
        self.makeup(f)
        with closing(sqlite3.connect(f.path)) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM item_locks WHERE item_uid=?',(coupon['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
