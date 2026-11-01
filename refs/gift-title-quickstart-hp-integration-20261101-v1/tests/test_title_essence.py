"""Real SQLite/codec regression for the shared title essence mutation."""
from pathlib import Path
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
import gc
from contextlib import closing
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
TASK=ROOT/'analysis'
TASK.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.titles import schema
from els_server.storage import boosting_2026_essence as storage
from els_server.domain.boosting_2026_essence import request,EssenceUseError
from els_server.domain.title_essence import rule_for
from els_server.protocol.protocol_codec import Event,encode_event,decode_event
from els_server.game_data import client_data

NOW=2_000_000_000
PAYLOAD=struct.pack('>BBii3f',0,0,0,0,10.,20.,0.)


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TASK,prefix='test-')
        self.path=Path(self.temp.name)/'own.sqlite3'
        self.account=LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET level=99 WHERE uid=1001')
            db.execute('UPDATE reward_balances SET experience=? WHERE uid=1001',(client_data().thresholds[98],))
            schema(db)
            db.execute("INSERT INTO title_ownership VALUES ('character',1001,13270,'synthetic',?,?)",(NOW-1,NOW+500))
            db.execute('INSERT INTO title_equipment VALUES (1001,13270)')
            db.execute('INSERT INTO inventory_items VALUES (9000001,1001,130208,2,3,4,0)')

    def tearDown(self):
        gc.collect()
        self.temp.cleanup()

    def state(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return dict(items=db.execute('SELECT * FROM inventory_items ORDER BY uid').fetchall(),
                        characters=db.execute('SELECT * FROM characters ORDER BY uid').fetchall(),
                        balances=db.execute('SELECT * FROM reward_balances ORDER BY uid').fetchall(),
                        receipts=db.execute('SELECT * FROM inventory_action_receipts ORDER BY operation_id').fetchall() if 'inventory_action_receipts'in tables else [])

    def invoke(self,op='op1',payload=PAYLOAD):
        return storage.action(self.path,1001,1,payload,op,now=NOW)

    def test_native_zero_skill_and_malformed_inputs(self):
        self.assertEqual(request(PAYLOAD),0)
        for payload in (b'',PAYLOAD[:-1],struct.pack('>BBii3f',0,0,0,-1,0,0,0),struct.pack('>BBii3f',1,0,0,0,0,0,0),struct.pack('>BBii3f',0,0,1,0,0,0,0),struct.pack('>BBii3f',0,0,0,0,float('nan'),0,0)):
            with self.subTest(payload=payload.hex()),self.assertRaises(ValueError):request(payload)

    def test_source_qualified_title_families(self):
        for title in (2060,12960,13050,13080,13100,2210,13200,13270,13290,2350):
            self.assertEqual(rule_for(title)['quantity'],1)
            self.assertEqual(rule_for(title)['interval_seconds'],30)
        for title in (40,1520,2120):self.assertIsNone(rule_for(title))

    def test_success_replay_and_cold_read(self):
        result=self.invoke()
        self.assertFalse(result['replayed'])
        e=result['events'][0]
        self.assertEqual((e.kind,struct.unpack_from('>iI',e.payload)),(0x461,(0,1)))
        self.assertEqual(decode_event(encode_event(e)).payload,e.payload)
        after=self.state()
        self.assertEqual(next(r[4]for r in after['items']if r[0]==9000001),2)
        replay=self.invoke()
        self.assertTrue(replay['replayed'])
        self.assertEqual([e.kind for e in replay['events']],[0x461,0x105])
        self.assertEqual(replay['events'][0].payload[-1],1)
        self.assertEqual(self.state(),after)
        self.assertEqual(next(i['count']for i in LocalAccount(LocalState(self.path)).get_inventory_snapshot()['items']if i['uid']==9000001),2)

    def test_last_material_removal_and_missing_material_text(self):
        for n in range(3):self.invoke(str(n))
        before=self.state()
        self.assertFalse(any(r[0]==9000001 for r in before['items']))
        with self.assertRaises(EssenceUseError)as error:self.invoke('empty')
        self.assertEqual(error.exception.result,2516)
        self.assertEqual(self.state(),before)

    def test_title_equipment_ownership_and_expiration(self):
        for change in ('UPDATE title_equipment SET title=0','UPDATE title_ownership SET expires_at=1999999999','DELETE FROM title_ownership'):
            with self.subTest(change=change):
                with closing(sqlite3.connect(self.path))as db,db:
                    db.execute('UPDATE title_equipment SET title=13270')
                    db.execute("INSERT OR REPLACE INTO title_ownership VALUES ('character',1001,13270,'synthetic',?,?)",(NOW-1,NOW+500))
                    db.execute(change)
                before=self.state()
                with self.assertRaises(EssenceUseError)as error:self.invoke(change)
                self.assertEqual(error.exception.result,503)
                self.assertEqual(self.state(),before)

    def test_locked_or_expired_material_is_not_consumed(self):
        from els_server.storage.item_locks import assign as lock
        from els_server.storage.item_expiration import assign as expire
        for assign,deadline in ((lock,NOW+1),(expire,NOW-1)):
            with self.subTest(assign=assign.__module__):
                with closing(sqlite3.connect(self.path))as db,db:
                    db.execute('BEGIN IMMEDIATE')
                    if assign is expire:db.execute('DELETE FROM item_locks')
                    assign(db,1001,9000001,deadline)
                before=self.state()
                with self.assertRaises(EssenceUseError)as error:self.invoke(assign.__module__)
                self.assertEqual(error.exception.result,2516)
                self.assertEqual(self.state(),before)

    def test_serialization_and_commit_failure_roll_back(self):
        for name in ('encode_event','_commit'):
            before=self.state()
            with self.subTest(name=name),patch.object(storage,name,side_effect=RuntimeError('forced')):
                with self.assertRaises(RuntimeError):self.invoke(name)
            self.assertEqual(self.state(),before)

    def test_foreign_account_and_conflicting_replay(self):
        before=self.state()
        with self.assertRaises(ValueError):storage.action(self.path,1001,2,PAYLOAD,'foreign',now=NOW)
        self.assertEqual(self.state(),before)
        self.invoke()
        after=self.state()
        with self.assertRaises(ValueError):self.invoke(payload=struct.pack('>BBii3f',0,0,0,0,11,20,0))
        self.assertEqual(self.state(),after)

    def test_existing_hyper_path(self):
        from els_server.domain.character_rules import CLASSES,default_slots
        from els_server.domain.skill_rules import learned_skills
        cls=next(k for k,v in CLASSES.items()if v['stage']==3 and v['base_class']==1)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET unit_class=?,transcendence=1 WHERE uid=1001',(cls,))
            db.execute('CREATE TABLE character_skill_seals (owner INTEGER NOT NULL,seal_group INTEGER NOT NULL,PRIMARY KEY(owner,seal_group))')
            db.executemany('INSERT INTO character_skill_seals VALUES (1001,?)',[(n,)for n in range(1,9)])
        c=self.account.character()
        hyper=next(s for s in learned_skills(c)if client_data().skill(s)['m_eType']==13)
        slots=list(default_slots(c));slots[20]=hyper
        self.account.save_skills(tuple(slots))
        result=self.invoke('hyper',struct.pack('>BBii3f',0,0,0,hyper,0,0,0))
        self.assertEqual(struct.unpack_from('>i',result['events'][0].payload)[0],0)

    def test_session_phase_lease_and_native_rejection(self):
        s=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        s.role='game';s.phase='dungeon_active'
        e=Event(0x202,kind=0x460,payload=PAYLOAD)
        with patch('els_server.storage.boosting_2026_essence.time.time',return_value=NOW):
            reply=s._handle(e,77)
        self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
        before=self.state()
        with patch('els_server.domain.dungeon_equipment_loot_flow.current_lease',return_value=False):
            self.assertEqual(struct.unpack_from('>i',s._handle(e,78)[0].payload)[0],503)
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE title_equipment SET title=0')
        with patch('els_server.storage.boosting_2026_essence.time.time',return_value=NOW):
            self.assertEqual(struct.unpack_from('>i',s._handle(e,79)[0].payload)[0],503)
        s.phase='town_ready'
        self.assertNotEqual(struct.unpack_from('>i',s._handle(e,80)[0].payload)[0],0)


if __name__=='__main__':
    unittest.main()
