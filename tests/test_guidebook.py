"""Native guidebook upload, durable reconnect and selected-character admission."""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace as NS
import sqlite3
import struct
import tempfile
import unittest

from els_server.protocol.protocol_codec import Event
from els_server.protocol import guidebook_messages as wire
from els_server.storage import guidebook as storage
from els_server.storage.local_state import LocalState
from els_server.domain import guidebook_flow as flow
from els_server.domain.local_session import LocalSession


class GuidebookTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'guidebook.sqlite3'
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER)')
            db.executemany('INSERT INTO characters VALUES (?)',[(1001,),(1002,),(1003,)])
            db.executemany('INSERT INTO character_owners VALUES (?,?)',[(1001,8),(1002,8),(1003,9)])
        self.session=self.actor(1001,8)

    def actor(self,uid,account_id):
        store=LocalState.__new__(LocalState);store.path=self.path;store.uid=uid
        account=NS(uid=uid,account_id=account_id,store=store,characters=object())
        account.root=NS(character_accounts={uid:account})
        s=NS(account=account,role='game',phase='town_ready',enter_town=True,
             client_build='dx11_260923',identity={'id':account_id},released=False)
        s.application=NS(accounts={account_id:account.root},playing={account_id:s})
        return s

    def upload(self,flags):
        return Event(0x202,performers=(0,),kind=0x812,payload=wire.initialization(flags).payload[4:])

    def saved(self,uid=1001,account_id=8):
        return storage.load(self.actor(uid,account_id).account.store,account_id)

    def test_first_open_repeated_upload_and_reconnect(self):
        # Read-only initialization of a pre-fix save does not create tables.
        self.assertEqual(flow.initialization(self.session).payload,struct.pack('>iI',0,0))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='guidebook_flags'").fetchone())
        event=self.upload({11:1,2:0,25:1})
        self.assertEqual(flow.handle(self.session,event),[])
        self.assertEqual(flow.handle(self.session,event),[])
        fresh=self.actor(1001,8)
        restored=flow.handle(fresh,Event(0x202,kind=0x810))[0]
        self.assertEqual(restored.kind,0x811)
        self.assertEqual(wire.request(restored.payload[4:]),{2:0,11:1,25:1})
        self.assertEqual(self.saved(1002),{})
        self.assertEqual(self.saved(1003,9),{})

    def test_whole_map_and_explicit_false_match_native(self):
        flow.handle(self.session,self.upload({11:1,25:1}))
        flow.handle(self.session,self.upload({11:0}))
        self.assertEqual(self.saved(),{11:0})

    def test_failed_replace_rolls_back(self):
        flow.handle(self.session,self.upload({11:1}))
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("CREATE TRIGGER fail_guidebook BEFORE INSERT ON guidebook_flags WHEN NEW.flag=25 BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):flow.handle(self.session,self.upload({11:0,25:1}))
        self.assertEqual(self.saved(),{11:1})

    def test_invalid_requests_cannot_replace_saved_flags(self):
        flow.handle(self.session,self.upload({11:1}))
        bad=[b'',struct.pack('>I',2)+struct.pack('>iB',11,1),
             struct.pack('>IiB',1,11,2),struct.pack('>IiB',1,0,1),
             struct.pack('>IiB',1,-1,1),struct.pack('>IiBiB',2,11,0,11,1),
             struct.pack('>I',0)+b'\x00']
        for payload in bad:
            with self.subTest(payload=payload),self.assertRaises(ValueError):
                flow.handle(self.session,Event(0x202,kind=0x812,payload=payload))
        self.assertEqual(self.saved(),{11:1})

    def test_owner_lease_phase_and_envelope_rejected(self):
        mutations=[lambda s:setattr(s,'phase','characters_ready'),
                   lambda s:setattr(s,'released',True),
                   lambda s:s.application.playing.update({8:object()}),
                   lambda s:setattr(s.account.store,'uid',1002),
                   lambda s:setattr(s.account,'account_id',9)]
        for mutate in mutations:
            s=self.actor(1001,8);mutate(s)
            with self.assertRaises(ValueError):flow.handle(s,self.upload({11:1}))
        with self.assertRaises(ValueError):
            flow.handle(self.actor(1003,8),self.upload({11:1}))
        for event in (Event(0x402,kind=0x812,payload=self.upload({11:1}).payload),
                      Event(0x202,uid=1002,kind=0x812,payload=self.upload({11:1}).payload)):
            with self.assertRaises(ValueError):flow.handle(self.session,event)
        self.assertEqual(self.saved(),{})

    def test_local_session_routes_upload_and_restores_before_ready(self):
        from els_server.domain.local_session import LocalAccount
        path=Path(self.temp.name)/'native-entry.sqlite3'
        def login():
            account=LocalAccount(LocalState(path));account.enable_characters()
            s=LocalSession(account,enter_town=True,client_build='dx11_260923')
            s.role='game';s.phase='characters_ready'
            replies=s.handle(Event(0x202,performers=(0,),kind=0x28,payload=struct.pack('>Q',1001)))
            kinds=[e.kind for e in replies]
            self.assertLess(kinds.index(0x2a),kinds.index(0x811))
            self.assertLess(kinds.index(0x811),kinds.index(0x29))
            return s,wire.request(next(e for e in replies if e.kind==0x811).payload[4:])
        first,flags=login()
        self.assertEqual(flags,{})
        self.assertEqual(first.handle(self.upload({11:1})),[])
        fresh,flags=login()
        self.assertEqual(flags,{11:1})
        self.assertEqual(fresh.handle(self.upload({11:1})),[])


if __name__=='__main__':unittest.main()
