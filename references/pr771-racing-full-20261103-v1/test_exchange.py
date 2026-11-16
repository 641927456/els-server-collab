from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import sqlite3,struct,sys,unittest
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime'
sys.path[:0]=[str(R),str(B)]
import test_secondbatch as base
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.reward_rules import item_plan
from els_server.protocol.protocol_codec import Event
from els_server.storage.mount_racing_exchange import exchange
from els_server.domain.tenebros_capacity_flow import selected


class Exchange(unittest.TestCase):
    def setUp(self):
        base.SecondBatch.setUp(self)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE location SET town=20013 WHERE uid=?',(self.a.uid,))
            self.source=grant_items(db,[item_plan(714109,40)],self.a.uid)[0]
        self.a.location=self.a.store.load();self.s.active_map=self.s.pending_map=20013
        self.payload=struct.pack('>iQiiiiiBi',40016,0,714109,20,0,1,1,1,0)
        self.path,self.owner,self.account_id,self.prepare=selected(self.s)

    def call(self,payload=None,operation='crystal1',prepare=None):
        return exchange(self.path,self.owner,self.account_id,20013,self.payload if payload is None else payload,operation,prepare=prepare or self.prepare)

    def state(self):
        with closing(sqlite3.connect(self.path))as db:
            return {t:db.execute('SELECT * FROM '+t+' ORDER BY 1,2').fetchall()for t, in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name NOT LIKE 'sqlite_%'ORDER BY name")}

    def test_real_native_entry_debit_grant_and_cold_retry(self):
        before=self.state();reply=self.s.handle(Event(0x202,kind=0x223,payload=self.payload,performers=(0,)),731)
        event,=[e for e in reply if e.kind==0x224];self.assertEqual(event.payload[:4],bytes(4))
        with closing(sqlite3.connect(self.path))as db:
            items=load_items(db,self.owner)
            self.assertEqual(sum(i['count']for i in items if i['template']==714109),20)
            self.assertEqual(sum(i['count']for i in items if i['template']==714108),1)
            self.assertEqual(db.execute('SELECT ed FROM reward_balances WHERE uid=?',(self.owner,)).fetchone()[0],before['reward_balances'][0][1])
        saved=self.state();self.s.handle(Event(0x202,kind=0x223,payload=self.payload,performers=(0,)),731)
        self.assertEqual(self.state(),saved)

    def test_batch_and_moved_current_receipt_projection(self):
        body=struct.pack('>iQiiiiiBi',40016,0,714109,20,0,1,2,1,0)
        self.call(body)
        with closing(sqlite3.connect(self.path))as db,db:
            product=next(i for i in load_items(db,self.owner)if i['template']==714108)
            db.execute('UPDATE inventory_items SET slot=6 WHERE uid=?',(product['uid'],))
        before=self.state();self.call(body);self.assertEqual(self.state(),before)
        with self.assertRaisesRegex(ValueError,'Conflicting'):self.call()
        self.assertEqual(self.state(),before)

    def test_qualification_and_failed_native_reply_without_increment(self):
        from els_server.domain.mount_racing_exchange_flow import handle
        before=self.state()
        for body in (self.payload[:-1],struct.pack('>iQiiiiiBi',40016,0,714109,19,0,1,1,1,0),struct.pack('>iQiiiiiBi',40016,0,714109,20,0,1,3,1,0)):
            answer=handle(self.s,Event(0x202,kind=0x223,payload=body),741)
            self.assertEqual(answer[0].payload[:4],struct.pack('>i',-1));self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE location SET town=20000 WHERE uid=?',(self.owner,))
        saved=self.state()
        with self.assertRaisesRegex(ValueError,'Saved Camilla'):self.call()
        self.assertEqual(self.state(),saved)

    def test_encode_and_late_actor_failure_roll_back_debit_and_grant(self):
        before=self.state()
        with patch('els_server.storage.mount_racing_exchange.acknowledgement',side_effect=ValueError('native encoder')):
            with self.assertRaisesRegex(ValueError,'native encoder'):self.call()
        self.assertEqual(self.state(),before)
        calls=[]
        def changed(db):
            calls.append(1)
            if len(calls)==2:self.s.phase='dungeon_active'
            self.prepare(db)
        try:
            with self.assertRaises(ValueError):self.call(prepare=changed)
        finally:self.s.phase='town_ready'
        self.assertEqual(self.state(),before)


if __name__=='__main__':unittest.main(verbosity=2)
