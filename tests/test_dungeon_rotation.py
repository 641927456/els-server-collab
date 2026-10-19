"""Native rotation reader, specialist selection and gate enforcement."""
import json,sqlite3,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from els_server.domain.dungeon_rotation import rotation,body,handle,notification
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.region_quests import account_dungeon_allowed
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.protocol.protocol_codec import Event

class DungeonRotationTests(unittest.TestCase):
    def test_original_reader_accepts_exact_array_extents(self):
        from role_native_replay import Replay
        wire=body();r=Replay();p=r.alloc(len(wire));r.write(p,wire)
        buf=r.alloc(48);r.write(buf+8,struct.pack('<QQQ',p,p+len(wire),p+len(wire)))
        stream=r.alloc(40);dto=r.alloc(32)
        r.call(0x3b6d140,stream);r.call(0x3b6d1c0,stream,buf,0)
        self.assertEqual(r.call(0x2be37d0,stream,dto)&255,1)
        self.assertEqual(int.from_bytes(r.read(buf+32,4),'little'),40)
        expected=json.loads((ROOT/'analysis/region-quests-20261015/native-rotation-reader.json').read_text())
        self.assertEqual(list(struct.unpack('<8i',r.read(dto,32))),expected['native_values'])

    def test_request_and_both_selection_checks(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.db';account=LocalAccount(LocalState(path));account.enable_characters()
            q=QuestState(path);q.snapshot()
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('UPDATE characters SET level=99 WHERE uid=1001')
            self.assertFalse(account_dungeon_allowed(account,35800))
            # This test isolates entrance authorization; transaction completion
            # of all 13 actual tasks is covered by test_region_quest_flow.
            with closing(sqlite3.connect(path)) as db,db:db.execute("INSERT INTO completed_quests VALUES (1001,27590,1,'{}')")
            for identity in [*rotation()['normal'],rotation()['story']]:self.assertTrue(account_dungeon_allowed(account,identity))
            self.assertFalse(account_dungeon_allowed(account,35810))
            s=LocalSession(account,client_build='dx11_260923');s.role='game';s.phase='town_ready'
            event=Event(0x202,performers=(0,),kind=0xccc)
            reply=handle(s,event)[0]
            self.assertEqual(reply.kind,0xccd);self.assertEqual(reply.payload,bytes(4)+notification().payload)
            self.assertEqual(handle(s,Event(0x202,performers=(0,),kind=0xccc,payload=b'bad'))[0].payload[:4],struct.pack('>i',-1))
            s.phase='characters_ready'
            self.assertEqual(handle(s,event)[0].payload[:4],struct.pack('>i',-1))

    def test_native_single_entry_uses_37f_and_echoes_admission_mode(self):
        from tests.test_dungeon_routes import ENTRY
        s=LocalSession(enter_town=True,enter_dungeon=True,client_build='dx11_260923',population_test=True,gate_test=True,npc_slot_test=True)
        s.role='game';s.phase='town_ready'
        request=lambda mode,identity:Event(0x202,kind=0x7d4,payload=struct.pack('>ii',mode,identity))
        # Native 7D5's returned mode chooses the local solo continuation.
        self.assertEqual(s.handle(request(2,30000))[0].payload,struct.pack('>ii',0,1))
        self.assertEqual(s.handle(Event(0x202,kind=0x37f,payload=ENTRY))[0].kind,0x380)
        self.assertEqual(s.phase,'town_ready')
        self.assertEqual(s.handle(request(2,35800))[0].payload,struct.pack('>ii',0,2))
        wrong=s.handle(Event(0x202,kind=0x382,payload=ENTRY))
        self.assertEqual(wrong[0].payload[:4],struct.pack('>i',-1))
        self.assertEqual(s.phase,'town_ready')
        reply=s.handle(Event(0x202,kind=0x37f,payload=ENTRY))
        self.assertEqual([e.kind for e in reply],[0x380,0x14a])
        self.assertEqual(reply[0].payload,bytes(20))
        self.assertEqual(s.dungeon_id,35800)
        self.assertEqual(s.phase,'dungeon_loading')

if __name__=='__main__':unittest.main()
