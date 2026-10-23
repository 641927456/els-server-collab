"""Current native inventory split cursors and full-restore protocol contract."""
import struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount,LocalSession,SessionOrderError
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import player_initialization
from els_server.protocol.bank_messages import restore_map

def ready(build='dx11_260923'):
    account=LocalAccount();account.accept_terms()
    session=LocalSession(account,enter_town=True,client_build=build)
    # Focus this source-only fixture on the 5BF state boundary. Full character
    # restoration and authentication are covered by the separate actual TLS QA.
    session.role='game';session.phase='skill_ui_ready'
    session.completed.update((0x1a,0x1e,0x35,0x1ef,0x485,0x28,0x6e9))
    return session

class InventorySplitContract(unittest.TestCase):
    def test_invalid_cursors_do_not_commit_phase(self):
        for payload in (b'',bytes(4),bytes(7),bytes(9),struct.pack('>ii',1,1),struct.pack('>ii',0,1),struct.pack('>ii',-1,0)):
            with self.subTest(payload=payload.hex()):
                session=ready();before=(session.phase,set(session.completed))
                with self.assertRaises(SessionOrderError):session.handle(Event(0x202,kind=0x5bf,payload=payload,performers=(0,)))
                self.assertEqual((session.phase,session.completed),before)

    def test_native_zero_cursors_replay_and_continue(self):
        session=ready();event=Event(0x202,kind=0x5bf,payload=bytes(8),performers=(0,))
        answer=session.handle(event)
        self.assertEqual([(e.kind,e.payload)for e in answer],[(0x5c0,bytes(12))])
        self.assertEqual(session.phase,'initialization_confirmed')
        self.assertEqual(session.handle(event),answer)
        self.assertEqual(session.handle(Event(0x202,kind=0x32,performers=(0,)))[0].kind,0x33)
        self.assertEqual(session.phase,'map_loading')

    def test_legacy_contract_is_preserved(self):
        self.assertEqual(ready('legacy').handle(Event(0x202,kind=0x5bf))[0].payload,bytes(12))

    def test_uninitialized_session_cannot_confirm(self):
        session=LocalSession(enter_town=True,client_build='dx11_260923')
        with self.assertRaises(SessionOrderError):session.handle(Event(0x202,kind=0x5bf,payload=bytes(8),performers=(0,)))
        self.assertEqual(session.phase,'new')

    def test_initial_restore_contains_nonempty_inventory(self):
        item=dict(uid=1001001,template=77000,metadata=2,count=3,group=6,slot=0)
        body=restore_map([item],[]);event=player_initialization(items=[item])
        self.assertEqual(struct.unpack_from('>I',body)[0],1)
        self.assertEqual(event.kind,0x2a)
        self.assertEqual(event.payload.count(body),1)

if __name__=='__main__':unittest.main()
