"""Owned99-level town actor; isolated reset transactions and native A8E flow."""
from pathlib import Path
import hashlib,json,sqlite3,struct,sys,unittest
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime'
sys.path[:0]=[str(R),str(B),str(ROOT/'analysis/pr771-racing-local-20261103-v1'),str(ROOT/'analysis/pr771-racing-local-20261103-v1/test-libs')]
import test_secondbatch as base
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.reward_rules import item_plan
from els_server.domain.mount_racing_rules import profile
from els_server.storage.mount_growth import save,read
from els_server.storage.mount_reset import perform
from els_server.domain.tenebros_capacity_flow import selected
from els_server.protocol.protocol_codec import Event

class Reset(unittest.TestCase):
    def setUp(self):
        base.SecondBatch.setUp(self)
        with closing(sqlite3.connect(self.path))as db,db:
            rows=grant_items(db,[item_plan(550431,1),item_plan(714108,2)],self.a.uid)
        self.crystal=next(i for i in rows if i['template']==714108)
        voucher=next(i for i in rows if i['template']==550431)
        activate(self.path,self.a.uid,0x432,struct.pack('>Q',voucher['uid']),'fixture-mount',account_id=self.a.account_id)
        self.mount=next(p for p in snapshot(self.path,self.a.uid)['companions']if p['kind']=='mount');self.uid=self.mount['uid']
        self.initial=profile(11300,{0:10,1:10,2:1,3:9})
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');save(db,self.a.uid,self.uid,self.initial)
        self.payload=struct.pack('>Q',self.uid)
        self.path,self.owner,self.account_id,self.prepare=selected(self.s)

    def call(self,operation='reset1',**kwargs):
        return perform(self.path,self.owner,self.account_id,self.payload,operation,prepare=self.prepare,**kwargs)

    def state(self):
        with closing(sqlite3.connect(self.path))as db:
            return {t:db.execute('SELECT * FROM '+t+' ORDER BY 1,2').fetchall()for t, in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name NOT LIKE 'sqlite_%'ORDER BY name")}

    def growth(self):
        with closing(sqlite3.connect(self.path))as db:return read(db,self.owner,self.uid)

    def test_success_atomic_cold_read_and_no_charge_on_replay(self):
        before=self.state();answer=self.call(randbelow=lambda n:0)
        self.assertEqual(answer[0].kind,0xa8f);self.assertEqual(answer[0].payload[:4],bytes(4))
        expected=profile(11300,{0:10,1:10,2:10});self.assertEqual(self.growth(),expected)
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(next(i for i in load_items(db,self.owner)if i['uid']==self.crystal['uid'])['count'],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mount_reset_receipts').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT ed FROM reward_balances WHERE uid=?',(self.owner,)).fetchone()[0],before['reward_balances'][0][1])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        frozen=self.state()
        def no_draw(n):raise AssertionError('Reset retry rerolled')
        self.assertEqual(self.call(randbelow=no_draw),answer)
        self.assertEqual(self.state(),frozen)
        self.assertEqual(next(p for p in snapshot(self.path,self.owner,enter_world=True)['companions']if p['uid']==self.uid)['racing'],expected)

    def test_final_crystal_removed_and_old_receipt_projects_latest_growth(self):
        self.call(randbelow=lambda n:0)
        self.call('reset2',randbelow=lambda n:n-1)
        expected=profile(11300,{1:10,2:10,3:10});self.assertEqual(self.growth(),expected)
        with closing(sqlite3.connect(self.path))as db:self.assertFalse(any(i['uid']==self.crystal['uid']for i in load_items(db,self.owner)))
        frozen=self.state();reply=self.call(randbelow=lambda n:1/0)[0]
        self.assertEqual(reply.payload[4:23],struct.pack('>QHBiI',self.uid,self.mount['unit'],20,11300,3))
        self.assertEqual(self.growth(),expected);self.assertEqual(self.state(),frozen)

    def test_wire_failure_and_selected_actor_change_roll_back_every_write(self):
        before=self.state()
        with patch('els_server.protocol.mount_messages.reset_ack',side_effect=ValueError('encode failure')):
            with self.assertRaisesRegex(ValueError,'encode failure'):self.call()
        self.assertEqual(self.state(),before)
        calls=[]
        def changed(db):
            calls.append(1)
            if len(calls)==2:self.s.phase='dungeon_active'
            self.prepare(db)
        try:
            with self.assertRaises(ValueError):perform(self.path,self.owner,self.account_id,self.payload,'actor-change',prepare=changed)
        finally:self.s.phase='town_ready'
        self.assertEqual(self.state(),before)

    def test_foreign_mount_wrong_account_malformed_and_conflicting_retry(self):
        before=self.state()
        for payload,account_id in [(b'',self.account_id),(self.payload+b'\0',self.account_id),(bytes(8),self.account_id),(struct.pack('>Q',self.uid+1),self.account_id),(self.payload,self.account_id+1)]:
            with self.assertRaises(ValueError):perform(self.path,self.owner,account_id,payload,'bad',prepare=self.prepare)
            self.assertEqual(self.state(),before)
        self.call();before=self.state()
        with closing(sqlite3.connect(self.path))as db,db:
            item=grant_items(db,[item_plan(550431,1)],self.owner)[0]
        activate(self.path,self.owner,0x432,struct.pack('>Q',item['uid']),'another-mount',account_id=self.account_id)
        other=next(p for p in snapshot(self.path,self.owner)['companions']if p['kind']=='mount'and p['uid']!=self.uid)
        before=self.state()
        with self.assertRaisesRegex(ValueError,'Conflicting'):perform(self.path,self.owner,self.account_id,struct.pack('>Q',other['uid']),'reset1',prepare=self.prepare)
        self.assertEqual(self.state(),before)

    def test_qualified_rejections_missing_crystal_low_level_and_no_growth(self):
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=98 WHERE uid=?',(self.owner,))
        before=self.state()
        with self.assertRaisesRegex(ValueError,'character level'):self.call()
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(self.owner,))
            db.execute('BEGIN IMMEDIATE')if not db.in_transaction else None
            save(db,self.owner,self.uid,profile())
        before=self.state()
        with self.assertRaisesRegex(ValueError,'earned points'):self.call()
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');save(db,self.owner,self.uid,self.initial)
            from els_server.storage.item_instances import remove
            remove(db,self.owner,self.crystal)
        before=self.state()
        with self.assertRaisesRegex(ValueError,'crystal required'):self.call()
        self.assertEqual(self.state(),before)

    def test_locked_expired_and_temporary_mount_rejections(self):
        from els_server.storage.item_locks import assign as lock
        from els_server.storage.item_expiration import assign as expire
        from els_server.storage.mount_state import assign_lifetime
        import time
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');lock(db,self.owner,self.crystal['uid'],int(time.time())+1000)
        before=self.state()
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM item_locks');expire(db,self.owner,self.crystal['uid'],int(time.time())-1000)
        before=self.state()
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM item_expiration');assign_lifetime(db,self.owner,self.mount,dict(group=4,slot=0,template=550431),1,int(time.time()))
        before=self.state()
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.state(),before)

    def test_real_session_a8e_and_bad_envelopes_do_not_mutate(self):
        e=Event(0x202,kind=0xa8e,performers=(0,),payload=self.payload)
        for bad in (replace(e,performers=(999,)),replace(e,uid=1001),replace(e,target_uid=1001),replace(e,payload_mode=1)):
            before=self.state();reply=self.s._handle(bad,5001)
            self.assertEqual(reply[0].kind,0xa8f);self.assertNotEqual(reply[0].payload[:4],bytes(4));self.assertEqual(self.state(),before)
        reply=self.s._handle(e,5002)
        self.assertEqual(reply[0].kind,0xa8f);self.assertEqual(reply[0].payload[:4],bytes(4),getattr(self.s,'_mount_reset_rejection',None))
        self.assertEqual(self.growth()['experience'],11300);self.assertEqual(sum(self.growth()['stats'].values()),30)
        before=self.state();self.s._handle(e,5002);self.assertEqual(self.state(),before)

    def test_automatic_selection_uses_a_usable_crystal_and_earliest_deadline(self):
        from els_server.storage.item_locks import assign as lock
        from els_server.storage.item_expiration import assign as expire
        import time
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');lock(db,self.owner,self.crystal['uid'],int(time.time())+1000)
            available=grant_items(db,[item_plan(714118,2)],self.owner)[0]
            expire(db,self.owner,available['uid'],int(time.time())+3000)
        self.call(randbelow=lambda n:0)
        with closing(sqlite3.connect(self.path))as db:
            items={i['uid']:i for i in load_items(db,self.owner)}
            self.assertEqual(items[self.crystal['uid']]['count'],2)
            self.assertEqual(items[available['uid']]['count'],1)
        with closing(sqlite3.connect(self.path))as db,db:db.execute('DELETE FROM item_locks')
        self.call('earliest-deadline',randbelow=lambda n:0)
        with closing(sqlite3.connect(self.path))as db:
            items={i['uid']:i for i in load_items(db,self.owner)}
            self.assertEqual(items[self.crystal['uid']]['count'],2)
            self.assertNotIn(available['uid'],items)

if __name__=='__main__':unittest.main()
