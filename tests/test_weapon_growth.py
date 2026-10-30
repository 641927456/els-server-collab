"""Weapon-specific progress and atomic rewards against fresh private saves."""
import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from els_server.domain import weapon_growth as rules
from els_server.domain.local_session import LocalAccount
from els_server.domain.local_artifact_rules import rating
from els_server.game_data import client_data
from els_server.storage import weapon_growth as store
from els_server.storage.inventory_state import load_items
from els_server.storage.local_state import LocalState
from els_server.storage.reward_state import RewardState


class WeaponGrowthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.db'
        self.account=LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.account.get_inventory_snapshot()
        self.item_uid=1002000
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=99 WHERE uid=1001')
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
                       (self.item_uid,1001,136062,client_data().item(136062)['metadata'],1,9,9))

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db,1001)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            return store.snapshot(db,1001,load_items(db,1001))

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def receipt(self,dungeon=34510):
        run_id=str(uuid.uuid4())
        evidence=('server-clear:'+run_id).encode()
        assessment=rating(dungeon,60,1,1,1)
        RewardState(self.path,1001,account_id=1).grant(
            run_id,evidence,0,0,response_builder=lambda balances,best:b'\0',
            dungeon_clear=(dungeon,60),clear_assessment=assessment,artifact_base=0)
        return run_id,evidence

    def clear(self,dungeon=34510):
        run,evidence=self.receipt(dungeon)
        return store.record_clear(self.path,1001,1,self.item_uid,run,dungeon,evidence)

    def claim(self,qid=1,operation='claim1',encode=lambda result:()):
        return store.claim(self.path,1001,1,self.item_uid,qid,operation,encode,now=1793300000+qid)

    def test_readonly_snapshot_initializes_real_task_without_writing(self):
        before=self.dump()
        state=self.snapshot()
        self.assertEqual(state['item_active'],[dict(id=1,owner=1001,item_uid=self.item_uid,started_at=0,objectives={1:0})])
        self.assertEqual(state['item_completed'],[])
        self.assertEqual(self.dump(),before)

    def test_whole_chain_rewards_native_options_and_reopens_cold(self):
        for q in rules.catalog()['quests']:
            for unused in range(q['target']):
                self.assertTrue(self.clear(q['dungeons'][0])['changed'])
            result=self.claim(q['id'],'claim'+str(q['id']))
            self.assertEqual(result['updated']['option_groups']['17'],q['options'])
            self.assertEqual(rules.stage(self.items()[0]),q['id'])
            self.assertEqual(len(result['state']['item_completed']),q['id'])
            next_active=self.snapshot()['item_active']
            if q['id']<5:
                self.assertEqual(next_active[0]['objectives'],{q['id']+1:0})
            else:
                self.assertEqual(next_active,[])

    def test_only_matching_committed_clear_counts_once(self):
        self.assertFalse(self.clear(30000)['changed'])
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{1:0})
        run,evidence=self.receipt()
        self.assertTrue(store.record_clear(self.path,1001,1,self.item_uid,run,34510,evidence)['changed'])
        self.assertFalse(store.record_clear(self.path,1001,1,self.item_uid,run,34510,evidence)['changed'])
        with self.assertRaises(ValueError):
            store.record_clear(self.path,1001,1,self.item_uid,run,34510,b'conflicting-proof')
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{1:1})

    def test_incomplete_stale_foreign_and_unequipped_claims_leave_no_increment(self):
        before=self.dump()
        for owner,account,qid,uid in [(1001,1,1,self.item_uid),(1001,2,1,self.item_uid),
                                      (1001,1,2,self.item_uid),(1001,1,1,self.item_uid+1)]:
            with self.assertRaises(ValueError):
                store.claim(self.path,owner,account,uid,qid,'rejected',lambda result:())
            self.assertEqual(self.dump(),before)
        self.clear()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE inventory_items SET bag_group=1,slot=0 WHERE uid=?',(self.item_uid,))
        before=self.dump()
        with self.assertRaises(ValueError):
            self.claim()
        self.assertEqual(self.dump(),before)

    def test_response_failure_rolls_back_reward_and_progress(self):
        self.clear()
        before=self.dump()
        def failed_encoder(result):
            raise ValueError('serialize failure')
        with self.assertRaisesRegex(ValueError,'serialize failure'):
            self.claim(encode=failed_encoder)
        self.assertEqual(self.dump(),before)
        self.assertEqual(rules.stage(self.items()[0]),0)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{1:1})

    def test_claim_replay_preserves_one_reward_and_conflicts_fail(self):
        self.clear()
        first=self.claim()
        before=self.dump()
        replay=self.claim()
        self.assertFalse(first['replayed'])
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['updated'],first['updated'])
        self.assertEqual(self.dump(),before)

    def test_old_claim_replay_sends_current_stage_after_later_growth(self):
        self.clear()
        self.claim()
        self.clear();self.clear()
        self.claim(2,'claim2')
        before=self.dump()
        result=self.claim()
        self.assertTrue(result['replayed'])
        self.assertEqual(result['quest_id'],1)
        self.assertEqual(rules.stage(result['updated']),2)
        self.assertEqual(result['state']['item_active'][0]['id'],3)
        self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):
            self.claim(2,'claim1')
        self.assertEqual(self.dump(),before)

    def test_uncommitted_or_wrong_owner_clear_is_rejected(self):
        before=self.dump()
        with self.assertRaises(ValueError):
            store.record_clear(self.path,1001,1,self.item_uid,str(uuid.uuid4()),34510,b'no-receipt')
        self.assertEqual(self.dump(),before)
        run,evidence=self.receipt()
        with closing(sqlite3.connect(self.path)) as db,db:
            row=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(run,)).fetchone()
            grant=json.loads(row[0]);grant['owner']=1002
            db.execute('UPDATE reward_receipts SET grant_json=? WHERE run_id=?',(json.dumps(grant),run))
        before=self.dump()
        with self.assertRaises(ValueError):
            store.record_clear(self.path,1001,1,self.item_uid,run,34510,evidence)
        self.assertEqual(self.dump(),before)

    def test_locked_weapon_can_grow_without_removing_lock(self):
        from els_server.storage.item_locks import assign
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            assign(db,1001,self.item_uid,2**62)
        self.clear()
        result=self.claim()
        self.assertEqual(result['updated']['lock_until'],2**62)
        self.assertEqual(rules.stage(self.items()[0]),1)

    def test_reward_vector_cannot_cross_stage_or_weapon_family(self):
        for q in rules.catalog()['quests']:
            self.assertEqual(rules.options(136062,q['options']),q['options'])
        for values in ([200086,200086],[200087],[200086,1]):
            with self.assertRaises(ValueError):
                rules.options(136062,values)
        with self.assertRaises(ValueError):
            rules.options(77000,[200086])


if __name__=='__main__':
    unittest.main()
