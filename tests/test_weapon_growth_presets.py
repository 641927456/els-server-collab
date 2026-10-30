"""Native full-growth presets are readable, without new growth tasks/awards."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from els_server.domain import weapon_growth as rules
from els_server.domain.inventory_items import validate_item,item_body
from els_server.domain.sage_sockets import capacity
from els_server.game_data import client_data
from els_server.storage import weapon_growth as growth
from els_server.storage.equipment_options import replace
from els_server.storage.inventory_state import load_items
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState


class WeaponGrowthPresetTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'save.db'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.account.get_inventory_snapshot();self.uid=1002000

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def insert(self,template,groups=None,group=1):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
                (self.uid,1001,template,client_data().item(template)['metadata'],1,group,9 if group==9 else 0))
            if groups is not None:replace(db,1001,self.uid,{},groups)

    def test_exact_fifteen_native_presets_are_separate_from_task_bindings(self):
        expected=set(range(720797,720813))-{720808}
        presets=rules.catalog()['presets']
        self.assertEqual({p['template'] for p in presets},expected)
        self.assertEqual(len(presets),15)
        for p in presets:
            with self.subTest(template=p['template']):
                self.assertEqual(p['stage'],5)
                self.assertEqual(p['options'],[47720,200148,200138])
                self.assertNotIn(p['template'],rules.templates())

    def test_all_presets_save_read_cold_and_encode_without_losing_other_groups(self):
        for p in rules.catalog()['presets']:
            with self.subTest(template=p['template']):
                groups={'0':[0]*capacity(p['template']),'17':p['options']}
                self.insert(p['template'],groups)
                before=self.dump()
                with closing(sqlite3.connect(self.path)) as db:
                    item=next(i for i in load_items(db,1001) if i['uid']==self.uid)
                    self.assertEqual(item['option_groups'],groups)
                    self.assertEqual(rules.stage(item),5)
                    self.assertEqual(growth.snapshot(db,1001,[item]),dict(item_active=[],item_completed=[]))
                    self.assertGreater(len(item_body(item)),304)
                self.assertEqual(self.dump(),before)
                cold=LocalAccount(LocalState(self.path));cold.enable_characters()
                restored=next(i for i in cold.get_inventory_snapshot()['items'] if i['uid']==self.uid)
                self.assertEqual(restored,item)
                with closing(sqlite3.connect(self.path)) as db,db:
                    from els_server.storage.item_instances import remove
                    db.execute('BEGIN IMMEDIATE');remove(db,1001,item)

    def test_bare_and_empty_vector_keep_native_max_stage_without_injection(self):
        for p in rules.catalog()['presets']:
            base=dict(uid=self.uid,template=p['template'],metadata=1,count=1,group=1,slot=0)
            for groups in (None,{}, {'17':[]}):
                item=dict(base)
                if groups is not None:item['option_groups']=copy.deepcopy(groups)
                before=copy.deepcopy(item)
                validate_item(item);self.assertEqual(rules.stage(item),5)
                self.assertEqual(item,before)

    def test_wrong_vectors_and_auxiliary_template_still_fail(self):
        for p in rules.catalog()['presets']:
            for values in ([47720],[47720,200148],[47720,200148,200137],[200086],['47720',200148,200138]):
                with self.subTest(template=p['template'],values=values),self.assertRaises(ValueError):
                    rules.options(p['template'],values)
        for template in (720808,136073,715116,77000):
            with self.assertRaises(ValueError):rules.options(template,[47720,200148,200138])

    def test_preset_claims_cannot_create_tasks_consume_or_award(self):
        self.insert(720797,{'17':[47720,200148,200138]},group=9)
        before=self.dump()
        for qid in (6,10):
            with self.assertRaises(ValueError):
                growth.claim(self.path,1001,1,self.uid,qid,'preset-claim',lambda result:())
            self.assertEqual(self.dump(),before)

    def test_failed_option_transaction_does_not_replace_prior_instance(self):
        sockets=[0]*capacity(720797)
        self.insert(720797,{'0':sockets})
        before=self.dump()
        with self.assertRaisesRegex(ValueError,'rollback'):
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('BEGIN IMMEDIATE')
                replace(db,1001,self.uid,{'0':sockets},{'0':sockets,'17':[47720,200148,200138]})
                raise ValueError('rollback')
        self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main()
