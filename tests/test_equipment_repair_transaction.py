import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from tests.historical_inventory import seed_existing_items as grant_items
from els_server.storage.equipment_durability import replace_durability
from els_server.storage.equipment_repair import repair
from els_server.domain.repair_pricing import require_baseline,catalog


def payload(*uids):return struct.pack('>I',len(uids))+b''.join(struct.pack('>Q',u) for u in uids)+bytes(6)


REPAIR_ACCOUNT_ID=1  # Explicit owner for this temporary database fixture.


class RepairTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3';self.account=LocalAccount(LocalState(self.path),account_id=REPAIR_ACCOUNT_ID);self.account.enable_characters()
        self.other=self.account.characters.create('RepairOther',5,'other')['uid'];self.account.for_character(self.other)
        with closing(sqlite3.connect(self.path)) as db,db:
            self.items=grant_items(db,[dict(template=30224,metadata=1,quantity=1,group=1),dict(template=100,metadata=1,quantity=1,group=1)])
            for i in self.items:replace_durability(db,1001,i['uid'],10000,1999)
            db.execute('UPDATE reward_balances SET ed=100000 WHERE uid=1001')
        self.request=payload(*(i['uid'] for i in self.items))

    def snapshot(self):return self.account.get_inventory_snapshot()

    def test_paid_repair_restart_and_replay_preserve_newer_state(self):
        before=self.snapshot();r=repair(self.path,1001,self.request,'one',account_id=REPAIR_ACCOUNT_ID)
        self.assertEqual(r['evidence']['ed_cost'],11201);self.assertEqual(r['balances']['ed'],88799)
        self.assertEqual(len(r['evidence']['after']),2)
        self.assertEqual(struct.unpack_from('>iQiiI',r['response']),(0,88799,0,0,2))
        self.assertTrue(all(i['durability']==10000 for i in r['evidence']['after']))
        # A newer wear/currency change must not be undone by old reply data.
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            replace_durability(db,1001,self.items[0]['uid'],10000,7000)
            db.execute('UPDATE reward_balances SET ed=12345,revision=revision+1 WHERE uid=1001')
        snapshot=self.snapshot();r=repair(self.path,1001,self.request,'one',account_id=REPAIR_ACCOUNT_ID)
        self.assertTrue(r['replayed'] and r['requires_inventory_sync']);self.assertEqual(r['balances']['ed'],12345)
        self.assertEqual(len(r['response']),24);self.assertEqual(r['inventory'],snapshot['items']);self.assertEqual(self.snapshot(),snapshot)
        restarted=LocalAccount(LocalState(self.path),account_id=REPAIR_ACCOUNT_ID);restarted.enable_characters();self.assertEqual(restarted.get_inventory_snapshot(),snapshot)

    def test_conflicts_foreign_items_modes_and_insufficient_ed(self):
        before=self.snapshot()
        for owner,req in [(self.other,self.request),(99999,self.request),(1001,payload(99)),(1001,payload(self.items[0]['uid'],self.items[0]['uid'])),(1001,self.request[:-1]),(1001,self.request[:-1]+b'\1')]:
            with self.assertRaises(ValueError):repair(self.path,owner,req,'invalid',account_id=REPAIR_ACCOUNT_ID)
        self.assertEqual(self.snapshot(),before)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=11200 WHERE uid=1001')
        before=self.snapshot()
        with self.assertRaises(ValueError):repair(self.path,1001,self.request,'short',account_id=REPAIR_ACCOUNT_ID)
        self.assertEqual(self.snapshot(),before)

    def test_encoding_failure_rolls_back_all_durability_and_ed(self):
        before=self.snapshot()
        with patch('els_server.storage.equipment_repair.acknowledgement',side_effect=RuntimeError('codec')):
            with self.assertRaises(RuntimeError):repair(self.path,1001,self.request,'one',account_id=REPAIR_ACCOUNT_ID)
        self.assertEqual(self.snapshot(),before)
        self.assertFalse(repair(self.path,1001,self.request,'one',account_id=REPAIR_ACCOUNT_ID)['replayed'])

    def test_competing_requests_and_id_conflict(self):
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda op:repair(self.path,1001,self.request,op,account_id=REPAIR_ACCOUNT_ID),['a','b']))
        self.assertEqual(sum(r['evidence']['ed_cost'] for r in rows),11201)
        self.assertEqual(self.snapshot()['balances']['ed'],88799)
        with self.assertRaises(ValueError):repair(self.path,1001,payload(self.items[0]['uid']),'a',account_id=REPAIR_ACCOUNT_ID)
        before=self.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:repair(self.path,1001,self.request,'a',account_id=REPAIR_ACCOUNT_ID),range(2)))
        self.assertTrue(all(r['replayed'] for r in rows));self.assertEqual(self.snapshot(),before)

    def test_foreign_account_cannot_replay_owned_repair_receipt(self):
        repair(self.path,1001,self.request,'owner-receipt',account_id=REPAIR_ACCOUNT_ID)
        before=self.snapshot()
        with closing(sqlite3.connect(self.path)) as db:
            receipt_before=db.execute('SELECT request_hash,owner,evidence_json FROM equipment_repair_receipts WHERE operation_id=?',('owner-receipt',)).fetchone()
        with self.assertRaises(ValueError):
            repair(self.path,1001,self.request,'owner-receipt',account_id=REPAIR_ACCOUNT_ID+1)
        self.assertEqual(self.snapshot(),before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT request_hash,owner,evidence_json FROM equipment_repair_receipts WHERE operation_id=?',('owner-receipt',)).fetchone(),receipt_before)
            self.assertEqual(db.execute('SELECT account_id FROM character_owners WHERE uid=?',(1001,)).fetchone(),(REPAIR_ACCOUNT_ID,))

    def test_unverified_discounts_are_never_authorized(self):
        d=catalog();self.assertEqual(len(d['template_effects']),158);self.assertEqual(len(d['title_effects']),6)
        for c,items in [(dict(unit_type=10),[]),(dict(unit_type=1,title=760),[]),(dict(unit_type=1,repair_buffs=[202]),[]),
                        (dict(unit_type=1),[dict(template=711611,group=4)]),(dict(unit_type=1),[dict(template=130261,group=9)])]:
            with self.assertRaises(ValueError):require_baseline(c,items)
        self.assertEqual(require_baseline(dict(unit_type=1),[dict(template=60100,group=9)]),1.0)

    def test_dispatch_requires_feature_phase_and_transport_identity(self):
        from els_server.config import ServerConfig
        from els_server.domain.local_session import LocalSession
        from els_server.protocol.protocol_codec import Event
        self.assertFalse(ServerConfig().session_options()['equipment_repair_enabled'])
        with self.assertRaises(ValueError):ServerConfig(equipment_repair_enabled=1)
        with self.assertRaises(ValueError):ServerConfig(profile='bootstrap',equipment_repair_enabled=True)
        session=LocalSession(self.account,**ServerConfig(equipment_repair_enabled=True).session_options())
        session.role='game';session.phase='characters_ready';event=Event(0x202,kind=0x18c,payload=self.request)
        before=self.snapshot()
        self.assertEqual(struct.unpack_from('>i',session.handle(event,1)[0].payload)[0],2)
        session.phase='town_ready'
        for sequence in (None,0,True,2**32):self.assertEqual(struct.unpack_from('>i',session.handle(event,sequence)[0].payload)[0],2)
        bad=Event(0x202,kind=0x18c,payload=payload(123))
        self.assertEqual(struct.unpack_from('>i',session.handle(bad,1)[0].payload)[0],100)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual([e.kind for e in session.handle(event,2)],[0x18d])
        before=self.snapshot();replay=session.handle(event,2)
        self.assertEqual(len(replay),2);self.assertEqual(replay[0].kind,0x18d)
        self.assertEqual(len(replay[0].payload),24);self.assertEqual(self.snapshot(),before)

    def test_zero_rate_repairs_and_revision_overflow_rollback(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            free=grant_items(db,[dict(template=3000,metadata=1,quantity=1,group=1)])[0]
            replace_durability(db,1001,free['uid'],10000,0)
            db.execute('UPDATE reward_balances SET ed=0,revision=? WHERE uid=1001',(2**63-1,))
        before=self.snapshot()
        with self.assertRaises(ValueError):repair(self.path,1001,payload(free['uid']),'overflow',account_id=REPAIR_ACCOUNT_ID)
        self.assertEqual(self.snapshot(),before)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET revision=1 WHERE uid=1001')
        result=repair(self.path,1001,payload(free['uid']),'free',account_id=REPAIR_ACCOUNT_ID)
        self.assertEqual(result['balances'],dict(ed=0,experience=0,revision=2))
        self.assertEqual(result['evidence']['after'][0]['durability'],10000)


if __name__=='__main__':unittest.main()
