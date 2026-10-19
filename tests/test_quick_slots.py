import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage.quick_slots import save_request,load,encode,decode,empty,initialization
from els_server.protocol.protocol_codec import Event


def request(values):return struct.pack('>i',1)+encode(values)


class QuickSlotsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('QuickOther',5,'other')['uid']
        self.account.for_character(self.other)
        with closing(sqlite3.connect(self.path)) as db,db:
            for count in (99,7):grant_items(db,[dict(template=77000,metadata=2,quantity=count,group=6)])

    def session(self):
        s=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,client_build='dx11_260923')
        s.role='game';s.phase='town_ready';return s

    def test_bind_clear_replay_restart_without_moving_inventory(self):
        before=self.account.get_inventory_snapshot();s=self.session()
        for values in ({**empty(),0:1},{**empty(),0:1,5:1},{**empty(),5:1}):
            event=Event(0x202,kind=0x8a1,payload=request(values))
            for seq in (1,1,2):
                reply=s.handle(event,seq)
                self.assertEqual([e.kind for e in reply],[0x8a2])
                self.assertEqual(reply[0].payload,bytes(4)+request(values))
                self.assertEqual(self.account.get_inventory_snapshot(),before)
        restarted=LocalAccount(LocalState(self.path));restarted.enable_characters()
        self.assertEqual(load(restarted.store.path),values)
        self.assertEqual(load(self.path,self.other),empty())
        # Native 8A0 now includes two explicit empty automatic pet slots.
        self.assertEqual(initialization(self.path).payload,encode(values)+struct.pack('>Iiiii',2,0,0,1,0))
        s.phase='dungeon_active'
        self.assertEqual(s.handle(Event(0x202,kind=0x8a1,payload=request(empty())),3)[0].payload[:4],bytes(4))
        self.assertEqual(load(self.path),empty())

    def test_bad_requests_and_foreign_owner_leave_state_unchanged(self):
        before=self.account.get_inventory_snapshot();good=request({**empty(),0:1})
        broken=[b'',good[:-1],good+bytes(1),struct.pack('>i',2)+good[4:],good[:4]+struct.pack('>I',5)+good[8:],
                good[:8]+struct.pack('>ii',6,1)+good[16:],good[:8]+struct.pack('>ii',-1,1)+good[16:],
                good[:8]+struct.pack('>ii',1,1)+good[16:],good[:12]+struct.pack('>i',-1)+good[16:],
                good[:12]+struct.pack('>i',81021)+good[16:]]
        for payload in broken:
            with self.assertRaises(ValueError):save_request(self.path,payload)
            self.assertEqual(load(self.path),empty())
        for owner in (self.other,999999):
            with self.assertRaises(ValueError):save_request(self.path,good,owner)
        s=self.session();s.role='frontend'
        self.assertEqual(s.handle(Event(0x202,kind=0x8a1,payload=good),1),[])
        s.role='game';s.phase='characters_ready'
        self.assertEqual(s.handle(Event(0x202,kind=0x8a1,payload=good),2)[0].payload[:4],struct.pack('>i',-1))
        self.assertEqual(self.account.get_inventory_snapshot(),before)

    def test_exhausted_binding_can_be_retained_and_cleared_without_minting(self):
        save_request(self.path,request({**empty(),0:1}))
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('DELETE FROM inventory_items WHERE owner=1001')
        values={**empty(),5:1};save_request(self.path,request(values))
        self.assertEqual(load(self.path),values)
        self.assertEqual(self.account.get_inventory_snapshot()['items'],[])
        save_request(self.path,request(empty()))
        with self.assertRaises(ValueError):save_request(self.path,request(values))

    def test_character_login_sends_full_map_and_does_not_leak_bindings(self):
        save_request(self.path,request({**empty(),5:1}))
        s=self.session();s.phase='characters_ready'
        first=s.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1001)),1)
        self.assertEqual(first[1].kind,0x8a0);self.assertEqual(first[1].payload,initialization(self.path).payload)
        s.phase='characters_ready'
        second=s.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',self.other)),2)
        self.assertEqual(second[1].payload,encode(empty())+struct.pack('>Iiiii',2,0,0,1,0))
