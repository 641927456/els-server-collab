"""Portable known-source role resurrection counter; no image, client or network."""
from contextlib import closing
from pathlib import Path
import sqlite3,struct,tempfile,unittest,uuid
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.known_resurrection import open_box,spend
from els_server.storage.resurrection_counter import snapshot
from els_server.protocol.known_resurrection import continuation,use_request,death_request

class KnownSourceResurrection(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='known-C-portable-');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'private.sqlite3'
        a=LocalAccount(LocalState(self.path),2,'known-fixture');a.enable_characters()
        self.uid=a.characters.create('KnownOne',1,'known-portable-role')['uid']
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            grant_items(db,[dict(template=190556,metadata=2,group=4,quantity=3)],self.uid)
            self.boxes=[i['uid']for i in load_items(db,self.uid)if i['template']==190556]
        self.guard=lambda:None
    def use(self,box):return struct.pack('>QBBBIi',box,0,0,0,0,0)
    def request(self):return struct.pack('>?QQ?',False,0,self.uid,False)
    def state(self):
        with closing(sqlite3.connect(self.path)) as db:return '\n'.join(db.iterdump())
    def open(self,box,operation,**options):
        return open_box(self.path,self.uid,self.use(box),operation,account_id=options.get('account_id',2),guard=options.get('guard',self.guard))
    def test_native_option_one_owned_box_consumes_once(self):
        payload=struct.pack('>QBBBIi',self.boxes[0],0,0,0,0,1)
        reply=open_box(self.path,self.uid,payload,'native-empty-confirm',account_id=2,guard=self.guard)
        self.assertEqual(snapshot(self.path,self.uid),10)
        self.assertEqual(struct.unpack_from('>i',reply[-1].payload,4)[0],10)
        committed=self.state()
        open_box(self.path,self.uid,payload,'native-empty-confirm',account_id=2,guard=self.guard)
        self.assertEqual(self.state(),committed)
        self.assertEqual(snapshot(self.path,self.uid),10)
    def test_native_option_one_foreign_owner_and_encode_failure_roll_back(self):
        from unittest.mock import patch
        payload=struct.pack('>QBBBIi',self.boxes[0],0,0,0,0,1)
        before=self.state()
        with self.assertRaises(ValueError):
            open_box(self.path,self.uid,payload,'foreign-option-one',account_id=3,guard=self.guard)
        self.assertEqual(self.state(),before)
        with patch('els_server.protocol.known_resurrection.encode_event',side_effect=ValueError('wire encode failure')):
            with self.assertRaisesRegex(ValueError,'wire encode failure'):
                open_box(self.path,self.uid,payload,'failed-option-one',account_id=2,guard=self.guard)
        self.assertEqual(self.state(),before)
    def test_unknown_option_choice_and_flags_never_consume_box(self):
        before=self.state()
        payloads=[struct.pack('>QBBBIi',self.boxes[0],0,0,0,0,mode)for mode in(-1,2,2147483647)]
        payloads += [struct.pack('>QBBBIii',self.boxes[0],0,0,0,1,30163,1),
                     struct.pack('>QBBBIi',self.boxes[0],2,0,0,0,1)]
        for index,payload in enumerate(payloads):
            with self.subTest(index=index),self.assertRaises(ValueError):
                open_box(self.path,self.uid,payload,'unknown-native-mode-'+str(index),account_id=2,guard=self.guard)
            self.assertEqual(self.state(),before)
    def test_current_counter_replay_and_once_per_life(self):
        before=self.state();self.assertEqual(snapshot(self.path,self.uid),0);self.assertEqual(self.state(),before)
        self.open(self.boxes[0],'open1')
        run=str(uuid.uuid4())
        first=spend(self.path,self.uid,self.request(),'spend1',run,1,account_id=2,guard=self.guard)
        self.assertEqual(first['count'],9);self.assertEqual([e.kind for e in first['events']],[0x161,0x162])
        self.assertEqual(struct.unpack_from('>i',self.open(self.boxes[0],'open1')[-1].payload,4)[0],9)
        self.open(self.boxes[1],'open2')
        self.assertEqual(struct.unpack_from('>i',self.open(self.boxes[0],'open1')[-1].payload,4)[0],19)
        before=self.state()
        self.assertEqual(spend(self.path,self.uid,self.request(),'spend1',run,1,account_id=2,guard=self.guard),dict(count=19,replayed=True))
        with self.assertRaises(ValueError):spend(self.path,self.uid,self.request(),'other-operation',run,1,account_id=2,guard=self.guard)
        self.assertEqual(self.state(),before)
    def test_owner_and_changed_context_roll_back_entire_mutation(self):
        before=self.state()
        with self.assertRaises(ValueError):self.open(self.boxes[0],'foreign',account_id=3)
        self.assertEqual(self.state(),before)
        calls=[]
        def changed():
            calls.append(True)
            if len(calls)==2:raise ValueError('changed playable context')
        with self.assertRaises(ValueError):self.open(self.boxes[0],'changed',guard=changed)
        self.assertEqual(self.state(),before)
    def test_prepare_failure_leaves_counter_and_spend_ledger_absent(self):
        self.open(self.boxes[0],'prepare-empty-ledger-credit')
        before=self.state();prepared=[]
        def reject(events):
            prepared.append([event.kind for event in events])
            raise ValueError('fixture peer queue preparation failure')
        with self.assertRaisesRegex(ValueError,'peer queue preparation failure'):
            spend(self.path,self.uid,self.request(),'prepare-empty-ledger-fail',str(uuid.uuid4()),1,
                  account_id=2,guard=self.guard,position=1,prepare=reject)
        self.assertEqual(prepared,[[0x161,0x162]])
        self.assertEqual(snapshot(self.path,self.uid),10)
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='known_resurrection_spends'").fetchone())
    def test_prepare_failure_preserves_prior_life_spend_and_counter(self):
        self.open(self.boxes[0],'prepare-existing-ledger-credit')
        run=str(uuid.uuid4())
        spend(self.path,self.uid,self.request(),'prepare-existing-ledger-first',run,1,
              account_id=2,guard=self.guard,position=1)
        before=self.state();prepared=[]
        def reject(events):
            prepared.append([event.kind for event in events])
            raise ValueError('fixture peer queue preparation failure')
        with self.assertRaisesRegex(ValueError,'peer queue preparation failure'):
            spend(self.path,self.uid,self.request(),'prepare-existing-ledger-fail',run,2,
                  account_id=2,guard=self.guard,position=1,prepare=reject)
        self.assertEqual(prepared,[[0x161,0x162]])
        self.assertEqual(snapshot(self.path,self.uid),9)
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT operation_id,owner,run,life FROM known_resurrection_spends').fetchall(),
                             [('prepare-existing-ledger-first',self.uid,run,1)])
    def test_native_wire_is_ordinary_self_known_counter_only(self):
        self.assertEqual(use_request(self.request(),self.uid),self.uid)
        with self.assertRaises(ValueError):use_request(struct.pack('>?QQ?',True,0,self.uid,False),self.uid)
        with self.assertRaises(ValueError):use_request(struct.pack('>?QQ?',False,0,self.uid+1,False),self.uid)
        ack,notice=continuation(self.uid,9)
        self.assertEqual(struct.unpack('>iiii?Q',ack.payload),(0,30000,9,0,False,self.uid))
        self.assertEqual(struct.unpack('>QQii',notice.payload),(self.uid,self.uid,-1,0))
        with self.assertRaises(ValueError):death_request(struct.pack('>iQQBffi?',-1,2**64-1,self.uid,0,float('nan'),0,-1,False))

if __name__=='__main__':unittest.main()
