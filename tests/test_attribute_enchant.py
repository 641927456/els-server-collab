import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage.attribute_enchant import change_attribute
from els_server.protocol.enchant_messages import request,acknowledgement


class AttributeEnchantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('EnchantOther',5,'other')['uid'];self.account.for_character(self.other)
        with closing(sqlite3.connect(self.path)) as db,db:
            self.gear=grant_items(db,[dict(template=30154,metadata=1,quantity=1,group=1)])[0]
            grant_items(db,[dict(template=130048,metadata=2,quantity=12,group=4),dict(template=130050,metadata=2,quantity=18,group=4)])
            db.execute('UPDATE reward_balances SET ed=100000 WHERE uid=1001')
        self.payload=struct.pack('>QBB',self.gear['uid'],0,1)

    def snapshot(self):return self.account.get_inventory_snapshot()

    def test_two_elements_replay_after_later_change_and_restart(self):
        first=change_attribute(self.path,1001,self.payload,'one')
        self.assertFalse(first['replayed']);self.assertEqual(first['evidence']['ed_cost'],1600)
        self.assertEqual(first['balances']['ed'],98400)
        self.assertEqual(struct.unpack_from('>iQQiBBI',first['response']),(0,98400,0,0,0,0,2))
        self.assertEqual(len(first['response']),30+340+324)
        self.assertEqual(next(i for i in first['inventory'] if i['uid']==self.gear['uid'])['attributes'],[1,0,0,0])
        self.assertEqual(next(i for i in first['inventory'] if i['template']==130048)['count'],6)
        second=change_attribute(self.path,1001,struct.pack('>QBB',self.gear['uid'],1,4),'two')
        self.assertEqual(second['balances']['ed'],93600)
        before=self.snapshot();replay=change_attribute(self.path,1001,self.payload,'one')
        self.assertTrue(replay['requires_inventory_sync']);self.assertTrue(replay['replayed'])
        self.assertEqual(len(replay['response']),30);self.assertEqual(replay['balances'],before['balances'])
        self.assertEqual(replay['inventory'],before['items']);self.assertEqual(self.snapshot(),before)
        restarted=LocalAccount(LocalState(self.path));restarted.enable_characters()
        self.assertEqual(restarted.get_inventory_snapshot(),before)

    def test_failed_requests_never_charge(self):
        before=self.snapshot()
        for payload in (b'',self.payload[:-1],self.payload+b'\0',struct.pack('>QBB',0,0,1),
                        struct.pack('>QBB',self.gear['uid'],4,1),struct.pack('>QBB',self.gear['uid'],0,8),
                        struct.pack('>QBB',self.gear['uid'],0,7),struct.pack('>QBB',self.gear['uid'],0,0),
                        struct.pack('>QBB',self.gear['uid'],1,1),struct.pack('>QBB',2**63,0,1)):
            with self.assertRaises(ValueError):change_attribute(self.path,1001,payload,'invalid')
        for owner in (self.other,99999):
            with self.assertRaises(ValueError):change_attribute(self.path,owner,self.payload,'foreign')
        self.assertEqual(self.snapshot(),before)
        change_attribute(self.path,1001,self.payload,'good');before=self.snapshot()
        for payload in (self.payload,struct.pack('>QBB',self.gear['uid'],1,2)):
            with self.assertRaises(ValueError):change_attribute(self.path,1001,payload,'new')
        with self.assertRaises(ValueError):change_attribute(self.path,1001,struct.pack('>QBB',self.gear['uid'],1,4),'good')
        self.assertEqual(self.snapshot(),before)

    def test_missing_material_and_currency_rollback(self):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=1599 WHERE uid=1001')
        before=self.snapshot()
        with self.assertRaises(ValueError):change_attribute(self.path,1001,self.payload,'short-ed')
        self.assertEqual(self.snapshot(),before)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE reward_balances SET ed=100000 WHERE uid=1001')
            db.execute('UPDATE inventory_items SET count=5 WHERE template=130048')
        before=self.snapshot()
        with self.assertRaises(ValueError):change_attribute(self.path,1001,self.payload,'short-crystal')
        self.assertEqual(self.snapshot(),before)

    def test_encoder_failure_rolls_back_every_write(self):
        before=self.snapshot()
        with patch('els_server.storage.attribute_enchant.acknowledgement',side_effect=RuntimeError('encoding failed')):
            with self.assertRaises(RuntimeError):change_attribute(self.path,1001,self.payload,'encode-fail')
        self.assertEqual(self.snapshot(),before)
        result=change_attribute(self.path,1001,self.payload,'encode-fail');self.assertFalse(result['replayed'])

    def test_multiple_stacks_exact_exhaustion_and_tombstones(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE inventory_items SET count=3 WHERE template=130048')
            # Deliberately split an existing legal stack to exercise depletion.
            row=db.execute('SELECT uid,owner,template,metadata,count,bag_group FROM inventory_items WHERE template=130048').fetchone()
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(row[0]+100,*row[1:],2))
        result=change_attribute(self.path,1001,self.payload,'split')
        self.assertEqual([x['quantity'] for x in result['evidence']['materials']],[3,3])
        self.assertEqual(len(result['response']),30+340+324*2)
        self.assertEqual(struct.unpack_from('>I',result['response'],26)[0],3)
        for offset in (370,694):self.assertEqual(struct.unpack_from('>Q',result['response'],offset)[0],0)
        self.assertFalse(any(i['template']==130048 for i in result['inventory']))

    def test_competing_and_duplicate_operations_debit_once(self):
        def attempt(operation):
            try:return change_attribute(self.path,1001,self.payload,operation)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['one','two']))
        self.assertEqual(sum(r is not None for r in results),1);self.assertEqual(self.snapshot()['balances']['ed'],98400)
        winner='one' if results[0] else 'two'
        with ThreadPoolExecutor(max_workers=2) as pool:replays=list(pool.map(attempt,[winner,winner]))
        self.assertTrue(all(r['replayed'] for r in replays));self.assertEqual(self.snapshot()['balances']['ed'],98400)

    def test_armor_capacity_and_special_equipment_exclusion(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            armor,special=grant_items(db,[dict(template=30224,metadata=1,quantity=1,group=1),dict(template=69865,metadata=1,quantity=1,group=1)])
        before=self.snapshot()
        with self.assertRaises(ValueError):change_attribute(self.path,1001,struct.pack('>QBB',special['uid'],0,1),'special')
        self.assertEqual(self.snapshot(),before)
        result=change_attribute(self.path,1001,struct.pack('>QBB',armor['uid'],0,1),'armor')
        self.assertEqual(result['evidence']['ed_cost'],250);self.assertEqual(result['evidence']['materials'][0]['quantity'],1)
        with self.assertRaises(ValueError):change_attribute(self.path,1001,struct.pack('>QBB',armor['uid'],1,1),'armor-full')

    def test_response_validation(self):
        self.assertEqual(request(self.payload),(self.gear['uid'],0,1))
        for balance in (-1,True,2**63):
            with self.assertRaises(ValueError):acknowledgement(balance)
        for changes in ([((1,1),self.gear)],[((1,0),self.gear)]*2,[((1,-1),None)]):
            with self.assertRaises(ValueError):acknowledgement(0,changes)

    def test_dispatch_phase_identity_and_replay_snapshot(self):
        from els_server.config import ServerConfig
        from els_server.domain.local_session import LocalSession
        from els_server.protocol.protocol_codec import Event
        self.assertFalse(ServerConfig().session_options()['attribute_enchant_enabled'])
        with self.assertRaises(ValueError):ServerConfig(attribute_enchant_enabled=1)
        options=ServerConfig(attribute_enchant_enabled=True).session_options()
        session=LocalSession(self.account,**options);session.role='game';session.phase='characters_ready'
        event=Event(0x202,kind=0x204,payload=self.payload);before=self.snapshot()
        self.assertEqual(session.handle(event,1)[0].payload[:4],struct.pack('>i',2))
        session.phase='town_ready'
        for sequence in (None,0,True,2**32):self.assertEqual(session.handle(event,sequence)[0].payload[:4],struct.pack('>i',2))
        self.assertEqual(before,self.snapshot())
        self.assertEqual([e.kind for e in session.handle(event,1)],[0x205])
        after=self.snapshot();replay=session.handle(event,1)
        self.assertEqual(len(replay),2);self.assertEqual(replay[0].kind,0x205);self.assertEqual(len(replay[0].payload),30)
        self.assertEqual(self.snapshot(),after)

    def test_remove_selected_slot_preserves_other_indices_and_materials(self):
        change_attribute(self.path,1001,self.payload,'fire')
        change_attribute(self.path,1001,struct.pack('>QBB',self.gear['uid'],1,4),'wind')
        before=self.snapshot();materials=[i for i in before['items'] if i['group']==4]
        removal=struct.pack('>QBB',self.gear['uid'],0,0)
        first=change_attribute(self.path,1001,removal,'remove-fire')
        self.assertEqual(first['evidence']['operation'],'remove');self.assertEqual(first['evidence']['materials'],[])
        self.assertEqual(first['evidence']['ed_cost'],9600);self.assertEqual(first['balances']['ed'],84000)
        self.assertEqual(next(i for i in first['inventory'] if i['uid']==self.gear['uid'])['attributes'],[0,4,0,0])
        self.assertEqual([i for i in first['inventory'] if i['group']==4],materials)
        self.assertEqual(len(first['response']),30+340)
        second=change_attribute(self.path,1001,struct.pack('>QBB',self.gear['uid'],1,0),'remove-wind')
        self.assertEqual(second['evidence']['ed_cost'],4800);self.assertEqual(second['balances']['ed'],79200)
        self.assertNotIn('attributes',next(i for i in second['inventory'] if i['uid']==self.gear['uid']))
        self.assertEqual(len(second['response']),30+324)
        self.assertEqual(change_attribute(self.path,1001,removal,'remove-fire')['inventory'],second['inventory'])
        from els_server.protocol.enchant_messages import EnchantRejected
        with self.assertRaises(EnchantRejected) as failed:change_attribute(self.path,1001,removal,'empty-slot')
        self.assertEqual(failed.exception.result,462)

    def test_native_failure_codes_and_remove_rollback(self):
        from els_server.protocol.enchant_messages import EnchantRejected
        change_attribute(self.path,1001,self.payload,'fire')
        before=self.snapshot()
        with patch('els_server.storage.attribute_enchant.acknowledgement',side_effect=RuntimeError('removal encode failure')):
            with self.assertRaises(RuntimeError):change_attribute(self.path,1001,struct.pack('>QBB',self.gear['uid'],0,0),'remove-fail')
        self.assertEqual(self.snapshot(),before)
        with self.assertRaises(EnchantRejected) as failed:change_attribute(self.path,1001,self.payload,'occupied')
        self.assertEqual(failed.exception.result,461)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=0 WHERE uid=1001')
        before=self.snapshot()
        for target,slot,code in ((0,0,658),(4,1,463)):
            with self.assertRaises(EnchantRejected) as failed:change_attribute(self.path,1001,struct.pack('>QBB',self.gear['uid'],slot,target),'poor')
            self.assertEqual(failed.exception.result,code)
        self.assertEqual(self.snapshot(),before)

    def test_remove_competes_without_double_charge(self):
        change_attribute(self.path,1001,self.payload,'fire')
        def attempt(op):
            try:return change_attribute(self.path,1001,struct.pack('>QBB',self.gear['uid'],0,0),op)
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['remove-a','remove-b']))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.snapshot()['balances']['ed'],93600)
