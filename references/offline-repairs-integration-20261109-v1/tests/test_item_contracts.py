"""Regression cases for persisted item locks, lifecycle and full consumption."""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sqlite3
import struct
import sys
import tempfile
import time
import unittest
import bootstrap

from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.domain.roster_account import RosterAccount
from els_server.storage import (expansion_items,skill_unlocks,titles,careers,artifact_progression,
    resonance_state,item_instances,item_locks,item_expiration,character_lifecycle,
    companion_state,ariel_attendance,inventory_actions,consumables,attribute_enchant,equipment_repair)
from els_server.domain import item_locks as lock_rules
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.skill_unlocks import catalog as books
from els_server.domain.quick_bindings import item_binding

WORK=bootstrap.WORK
NOW=int(time.time())
FAMILIES=('expansion','skill','title','career','artifact')


class OwnedFixture:
    def __init__(self,family='expansion'):
        self.directory=tempfile.TemporaryDirectory(prefix='owned-items-',dir=WORK)
        self.path=Path(self.directory.name)/'state.sqlite3'
        with closing(sqlite3.connect(self.path)) as db,db:
            from els_server.storage.local_state import ensure_local_tables
            from els_server.storage.reward_state import ensure_reward_tables
            from els_server.storage.inventory_state import ensure_inventory
            ensure_local_tables(db);ensure_reward_tables(db);ensure_inventory(db)
        roster=RosterAccount(self.path,1,'owned')
        created=roster.characters.create('OwnedRole',1,'owned-create')
        if created['uid']!=1001:raise AssertionError('Unexpected first owned fixture UID')
        self.account=roster.for_character(1001)
        self.family=family
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=99 WHERE uid=1001')
            db.execute('UPDATE reward_balances SET ed=100000000 WHERE uid=1001')
            if family in ('skill','artifact'):
                db.execute('UPDATE characters SET unit_class=150,transcendence=1,master=1 WHERE uid=1001')
                db.execute("INSERT OR REPLACE INTO character_artifacts VALUES(1001,1,1,1,0,'[0,0,0,0]')")
        templates=dict(expansion=274160,skill=next(r['template']for r in books()['books'].values()if r['seal_group']==1),
                       title=81650,career=214410,artifact=711315,resonance=163561)
        self.template=templates.get(family,274160)
        self.item=self.add(self.template)
        self.payload=struct.pack('>QQiiIB',self.item['uid'],0,0,0,0,0)

    def close(self):self.directory.cleanup()

    def add(self,template,count=1,*,lock=None,expiry=None):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            group=TEMPLATE_BAG_GROUPS[template]
            occupied={r[0]for r in db.execute('SELECT slot FROM inventory_items WHERE owner=1001 AND bag_group=?',(group,))}
            slot=next(i for i in range(36)if i not in occupied)
            item=dict(uid=item_instances.next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],count=count,group=group,slot=slot)
            if lock is not None:item['lock_until']=lock
            if expiry is not None:item['expires_at']=expiry
            item_instances.insert(db,1001,item)
            return item

    def lock(self,until):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');item_locks.assign(db,1001,self.item['uid'],until)

    def lifecycle(self,finalized=False):
        with closing(sqlite3.connect(self.path)) as db,db:
            character_lifecycle.initialize(db)
            db.execute('''INSERT INTO character_lifecycle(uid,account_id,created_at,requested_at,finalized_at)
                VALUES(1001,1,1,10,?) ON CONFLICT(uid) DO UPDATE SET requested_at=10,finalized_at=excluded.finalized_at''',
                (20 if finalized else 0,))

    def restore(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE character_lifecycle SET requested_at=0,finalized_at=0 WHERE uid=1001')

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return tuple(db.iterdump())

    def use(self,operation='owned-use'):
        if self.family=='expansion':return expansion_items.use_expansion_item(self.path,1001,self.payload,operation)
        if self.family=='skill':return skill_unlocks.use_skill_book(self.path,1001,self.payload,operation)
        if self.family=='title':return titles.use_item(self.path,1001,self.payload,operation,now=NOW)
        if self.family=='career':return careers.use_career_item(self.path,1001,self.payload,operation)
        if self.family=='artifact':return artifact_progression.action(self.path,1001,'potion',self.payload,operation,account_id=1)
        if self.family=='resonance':return resonance_state.use_book(self.path,1001,1,self.payload,operation)
        raise AssertionError(self.family)


class ItemContracts(unittest.TestCase):
    def fixture(self,family='expansion'):
        value=OwnedFixture(family);self.addCleanup(value.close);return value

    def test_new_mutations_reject_pending_and_finalized_characters(self):
        for family in FAMILIES:
            for finalized in (False,True):
                with self.subTest(family=family,finalized=finalized):
                    f=self.fixture(family);f.lifecycle(finalized);before=f.dump()
                    with self.assertRaisesRegex(ValueError,'pending deletion or finalized'):f.use()
                    self.assertEqual(f.dump(),before)

    def test_committed_replays_reject_retired_actor_and_work_after_restore(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                f=self.fixture(family);f.use();f.lifecycle();before=f.dump()
                with self.assertRaisesRegex(ValueError,'pending deletion or finalized'):f.use()
                self.assertEqual(f.dump(),before)
                f.restore();before=f.dump();f.use();self.assertEqual(f.dump(),before)

    def test_locked_books_are_rejected_before_unlocking_or_consuming(self):
        for family in ('expansion','skill'):
            with self.subTest(family=family):
                f=self.fixture(family);f.lock(NOW+3600);before=f.dump()
                with self.assertRaisesRegex(ValueError,'locked'):f.use()
                self.assertEqual(f.dump(),before)

    def test_elapsed_locks_allow_use_and_leave_no_orphan_lock(self):
        for family in (*FAMILIES,'resonance'):
            with self.subTest(family=family):
                f=self.fixture(family);f.lock(NOW-10);f.use()
                with closing(sqlite3.connect(f.path)) as db:
                    self.assertIsNone(db.execute('SELECT 1 FROM inventory_items WHERE uid=?',(f.item['uid'],)).fetchone())
                    self.assertIsNone(db.execute('SELECT 1 FROM item_locks WHERE item_uid=?',(f.item['uid'],)).fetchone())
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_resonance_lock_boundary_matches_shared_native_rule(self):
        f=self.fixture('resonance');f.lock(NOW);before=f.dump()
        with patch.object(lock_rules,'time',SimpleNamespace(time=lambda:NOW)),patch.object(resonance_state,'time',SimpleNamespace(time=lambda:NOW)):
            with self.assertRaisesRegex(ValueError,'locked'):f.use()
        self.assertEqual(f.dump(),before)

    def test_title_equipment_rejects_pending_actor(self):
        f=self.fixture('title');f.use();f.lifecycle();before=f.dump()
        with self.assertRaisesRegex(ValueError,'pending deletion or finalized'):titles.equip(f.path,1001,10970)
        self.assertEqual(f.dump(),before)

    def test_book_encoder_failure_rolls_back_unlock_and_consumption(self):
        for family,module in (('expansion',expansion_items),('skill',skill_unlocks)):
            with self.subTest(family=family):
                f=self.fixture(family);before=f.dump()
                with patch.object(module,'use_ack',side_effect=ValueError('owned encoding failure')):
                    with self.assertRaisesRegex(ValueError,'owned encoding failure'):f.use()
                self.assertEqual(f.dump(),before)

    def test_pet_activation_cleans_elapsed_lock(self):
        f=self.fixture();item=f.add(500000,lock=NOW-10)
        payload=struct.pack('>Q',item['uid'])+struct.pack('>I',len('OwnedPet'.encode('utf-16le')))+'OwnedPet'.encode('utf-16le')
        companion_state.handle(f.path,1001,0x2e8,payload,'owned-pet',account_id=1)
        with closing(sqlite3.connect(f.path)) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM item_locks WHERE item_uid=?',(item['uid'],)).fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM companions WHERE owner=1001').fetchone()[0],1)

    def test_expiry_cleans_item_state_and_keeps_registration_history(self):
        f=self.fixture();item=f.add(77000,expiry=NOW-10,lock=NOW-20)
        with closing(sqlite3.connect(f.path)) as db,db:
            from els_server.storage.wardrobe import ensure
            db.execute('BEGIN');ensure(db)
            db.execute('INSERT INTO wardrobe_item_state VALUES(?,0,0)',(item['uid'],))
            db.execute("INSERT INTO wardrobe_dyes VALUES(?,'[0,0,0]','[0,0,0]')",(item['uid'],))
            db.execute('INSERT INTO wardrobe_account_sources VALUES(1,?,?,1001)',(item['uid'],item['template']))
        result=item_expiration.remove_due(f.path,1001,now=NOW)
        self.assertTrue(result)
        with closing(sqlite3.connect(f.path)) as db:
            for table in ('item_locks','item_expiration','wardrobe_item_state','wardrobe_dyes'):
                self.assertIsNone(db.execute('SELECT 1 FROM '+table+' WHERE item_uid=?',(item['uid'],)).fetchone(),table)
            self.assertEqual(db.execute('SELECT count(*) FROM wardrobe_account_sources').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        before=f.dump();self.assertEqual(item_expiration.remove_due(f.path,1001,now=NOW),[]);self.assertEqual(f.dump(),before)

    def test_discard_cleans_expired_lock_and_linked_appearance(self):
        f=self.fixture();item=f.add(77000,lock=NOW-10)
        with closing(sqlite3.connect(f.path)) as db,db:
            from els_server.storage.wardrobe import ensure
            db.execute('BEGIN');ensure(db)
            db.execute('INSERT INTO wardrobe_item_state VALUES(?,0,0)',(item['uid'],))
        inventory_actions.discard(f.path,1001,struct.pack('>Qi',item['uid'],1),'owned-discard')
        with closing(sqlite3.connect(f.path)) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM wardrobe_item_state WHERE item_uid=?',(item['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_random_box_exhaustion_cleans_elapsed_lock(self):
        from els_server.storage.ice_state import draw
        f=self.fixture();item=f.add(163362,lock=NOW-10)
        payload=struct.pack('>QBBBIi',item['uid'],0,0,0,0,0)
        draw(f.path,payload,'owned-box',randbelow=lambda n:0)
        with closing(sqlite3.connect(f.path)) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM item_locks WHERE item_uid=?',(item['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
