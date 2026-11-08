"""Exercise persisted friend lifecycle and mailbox consumers without a server."""
from contextlib import closing, ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sqlite3
import struct
import sys
import tempfile
import unittest

import bootstrap
WORK = bootstrap.WORK
from els_server.domain import friend_flow, mailbox_extras as mail_flow
from els_server.domain.friends_world import Mailbox
from els_server.protocol import friend_messages
from els_server.protocol.mail_notifications_2026 import notice
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.storage import character_lifecycle, friend_state, game_mail
from els_server.storage import mailbox_extras, online_2026_mail_snapshot, relationship_mail


class Fixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='owned-offline-', dir=WORK)
        self.path = Path(self.directory.name) / 'fixture.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''CREATE TABLE characters(uid INTEGER PRIMARY KEY, name TEXT,
                name_key TEXT, unit_type INTEGER, unit_class INTEGER, level INTEGER,
                revision INTEGER NOT NULL DEFAULT 0)''')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY, account_id INTEGER)')
            db.executemany('INSERT INTO characters VALUES(?,?,?,1,1,99,0)', (
                (uid, 'Role'+str(uid), 'role'+str(uid)) for uid in range(1001,1009)
            ))
            db.executemany('INSERT INTO character_owners VALUES(?,?)', (
                (uid, uid-1000) for uid in range(1001,1009)
            ))

    def tearDown(self):
        self.directory.cleanup()

    def saved(self):
        with closing(sqlite3.connect(self.path)) as db:
            return '\n'.join(db.iterdump())


class FriendLifecycle(Fixture):
    def setUp(self):
        super().setUp()
        with closing(sqlite3.connect(self.path)) as db, db:
            friend_state.ensure(db)

    def edge(self, target, status=0, blocked=0):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO native_friend_edges VALUES(1001,?,?,?,0,?,1)',
                       (target,status,blocked,'hello'))
            opposite = {0:0,1:2,2:1}[status]
            db.execute('INSERT INTO native_friend_edges VALUES(?,1001,?,0,0,?,1)',
                       (target,opposite,'hello'))

    def retire(self, uid, *, pending=False):
        with closing(sqlite3.connect(self.path)) as db, db:
            character_lifecycle.initialize(db)
            db.execute('''INSERT INTO character_lifecycle
                (uid,account_id,created_at,requested_at,finalize_at,finalized_at)
                VALUES(?,?,1,10,20,?)''', (uid,uid-1000,0 if pending else 30))
            if not pending:
                db.execute('UPDATE characters SET name_key=? WHERE uid=?',(':deleted:'+str(uid),uid))

    def snapshot(self, online=None):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN')
            return friend_state.snapshot(db,1001,1,online or {})

    def test_finalized_friends_requests_and_blocks_are_hidden(self):
        for uid,status,blocked in [(1002,0,0),(1003,0,0),(1004,0,1),(1005,1,0),(1006,2,0)]:
            self.edge(uid,status,blocked)
        self.retire(1003,pending=True)
        for uid in (1004,1005,1006):
            self.retire(uid)
        before = self.saved()
        state = self.snapshot()
        self.assertEqual([row['uid'] for row in state['friends']],[1002,1003])
        self.assertEqual(state['pending'],[])
        self.assertEqual(self.saved(),before)
        # The cold-login serializer consumes the filtered snapshot directly.
        cold = Event(0x201,kind=0x2f,payload=bytes(55))
        restored = friend_messages.restore(cold,state)
        self.assertEqual(struct.unpack_from('>I',restored.payload,43)[0],2)
        encode_event(restored)

    def test_legacy_database_retains_live_friend_and_pending_request(self):
        self.edge(1002)
        self.edge(1003,2)
        before = self.saved()
        state = self.snapshot()
        self.assertEqual([row['uid'] for row in state['friends']],[1002,1003])
        self.assertEqual([row['uid'] for row in state['pending']],[1003])
        self.assertEqual(self.saved(),before)

    def test_actual_finalization_disappears_on_next_cold_read(self):
        self.edge(1002)
        self.retire(1002,pending=True)
        self.assertEqual(len(self.snapshot()['friends']),1)
        result = character_lifecycle.change(self.path,2,1002,'finalize')
        self.assertEqual(result['operation'],'finalize')
        self.assertEqual(self.snapshot()['friends'],[])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM native_friend_edges').fetchone()[0],2)

    def test_old_friend_can_be_removed_and_retry_reuses_receipt(self):
        self.edge(1002)
        self.retire(1002)
        def remove():
            return friend_state.perform(self.path,1001,1,0x257,struct.pack('>Q',1002),
                dict(target=1002),'owned-delete-friend',lambda db: None,
                lambda db,result,notices,repeated: (result,friend_state.snapshot(db,1001,1,{}),repeated))
        first, second = remove(), remove()
        self.assertFalse(first[2])
        self.assertTrue(second[2])
        self.assertEqual(first[:2],second[:2])
        self.assertEqual(second[1]['friends'],[])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM native_friend_operations').fetchone()[0],1)

    def test_finalized_presence_produces_no_delivery(self):
        self.edge(1002)
        self.retire(1002)
        sender = SimpleNamespace(account=SimpleNamespace(uid=1002))
        peer = Peer(1001,1)
        with closing(sqlite3.connect(self.path)) as db, ExitStack() as locks:
            db.execute('BEGIN')
            boxes = friend_flow.presence_boxes(sender,db,{1001:peer},[],locks)
        self.assertEqual(boxes,{})
        self.assertEqual(peer.mailbox.drain(),[])

    def test_live_presence_still_uses_bounded_original_wire(self):
        self.edge(1002)
        sender, peer = Peer(1002,2), Peer(1001,1)
        with closing(sqlite3.connect(self.path)) as db, ExitStack() as locks:
            db.execute('BEGIN')
            boxes = friend_flow.presence_boxes(sender,db,{1001:peer,1002:sender},[],locks)
        self.assertEqual(len(boxes),1)
        message = boxes[peer].drain()[0]
        self.assertEqual(message.kind,0x262)
        self.assertEqual(struct.unpack_from('>IQ',message.payload),(1,1002))
        self.assertEqual(peer.mailbox.drain(),[])

    def test_wrong_owner_cannot_read_friends(self):
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(ValueError):
                friend_state.snapshot(db,1001,2,{})


class Peer:
    def __init__(self,uid,account):
        self.account = SimpleNamespace(uid=uid,account_id=account)
        self.active_map = 100
        self.mailbox = Mailbox()


def unread_counts(event):
    if event.kind != 0x1ce:
        raise AssertionError('Expected native mailbox notice')
    raw, result = event.payload, {}
    length = struct.unpack_from('>I',raw)[0]
    for index in range(length):
        folder,count = struct.unpack_from('>Bi',raw,4+index*5)
        if folder in result:
            raise AssertionError('Duplicate mailbox folder')
        result[folder] = count
    offset = 4+length*5
    if raw[offset:] != bytes(5):
        raise AssertionError('Expected empty previews and original false flag')
    encode_event(event)
    return result


class MailFolders(Fixture):
    def setUp(self):
        super().setUp()
        with closing(sqlite3.connect(self.path)) as db, db:
            # Two characters on account 1 exercise recipient isolation.
            db.execute('UPDATE character_owners SET account_id=1 WHERE uid=1002')
            game_mail.ensure(db)
            db.execute(relationship_mail.SCHEMA)
            db.execute('''CREATE TABLE native_guild_reward_mail_v2(
                operation TEXT PRIMARY KEY,mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),
                owner INTEGER NOT NULL,guild_id INTEGER NOT NULL,source_json TEXT NOT NULL)''')
            db.execute('''CREATE TABLE online2026_mail_scope(mail_id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,recipient_uid INTEGER NOT NULL,deadline INTEGER NOT NULL)''')
            db.executemany('''INSERT INTO game_mail
                (id,campaign,account_id,sender,title,body,ed,created_at,expires_at,read_at,deleted_at)
                VALUES(?,?,?,'Sender','Title','Body',0,1,?,?,?)''', (
                (mid,'owned-mail-'+str(mid),account,expiry,read,deleted)
                for mid,account,expiry,read,deleted in [
                    (1,1,1000,None,None),(2,1,1000,None,None),(3,1,1000,None,None),
                    (4,1,1000,None,None),(5,1,1000,None,None),(6,1,1000,100,None),
                    (7,1,150,None,None),(8,1,1000,None,100),(9,3,1000,None,None),
                ]
            ))
            db.executemany('INSERT INTO player_mail_meta VALUES(?,?,2,1003,NULL,NULL)',
                           ((2,1001),(5,1002),(6,1001)))
            db.execute("INSERT INTO native_relationship_mail VALUES('owned-bond',3,1001,'owned-pair',NULL,22,1,1)")
            db.execute("INSERT INTO native_guild_reward_mail_v2 VALUES('owned-guild',4,1001,1,'{}')")
            db.execute('INSERT INTO online2026_mail_scope VALUES(1,1,1001,1000)')
        self.session = SimpleNamespace(client_build='dx11_260923',role='game',phase='town_ready',
            item_test=True,account=SimpleNamespace(account_id=1,uid=1001,
                                                   store=SimpleNamespace(path=self.path)))
        self.clock = patch.object(mail_flow,'time',SimpleNamespace(monotonic=lambda:500,time=lambda:200))
        self.clock.start()
        self.store_clock = patch.object(mailbox_extras,'time',SimpleNamespace(time=lambda:200))
        self.store_clock.start()
        mail_flow._maintenance_after[str(self.path)] = 999
        mail_flow._anniversary_after[(str(self.path),1,1001)] = 999
        mail_flow._anniversary_after[(str(self.path),1,1002)] = 999

    def tearDown(self):
        self.store_clock.stop()
        self.clock.stop()
        mail_flow._maintenance_after.pop(str(self.path),None)
        for uid in (1001,1002):
            mail_flow._anniversary_after.pop((str(self.path),1,uid),None)
        super().tearDown()

    def snapshot(self,uid=1001):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN')
            return online_2026_mail_snapshot.snapshot(db,account=1,character=uid,now=200)

    def test_shared_snapshot_matches_inbox_folders_and_scope(self):
        before = self.saved()
        value = self.snapshot()
        self.assertEqual(value['unread_counts'],{0:1,1:1,2:1,3:1,4:0})
        self.assertEqual(value['visible_unread_ids'],(4,3,2,1))
        self.assertEqual(value['activity_unread_ids'],(1,))
        self.assertEqual(mailbox_extras.status(self.path,1,1001,now=200),(5,4,6))
        for folder in range(5):
            total, rows = game_mail.inbox(self.path,1,1001,folder=folder,now=200)
            self.assertEqual(sum(row['read_at'] is None for row in rows),value['unread_counts'][folder])
        self.assertEqual(self.saved(),before)

    def test_periodic_and_manual_refresh_send_all_folders(self):
        expected = {0:1,1:1,2:1,3:1,4:0}
        self.assertEqual(unread_counts(mail_flow.periodic(self.session,force=True)[0]),expected)
        response = mail_flow.handle(self.session,Event(0x202,kind=0xc09,payload=b''))
        self.assertEqual(response[0].kind,0xc0a)
        self.assertEqual(response[0].payload,bytes(4))
        self.assertEqual(unread_counts(response[1]),expected)

    def test_folder_move_changes_notice_even_when_total_and_max_id_do_not(self):
        mail_flow.periodic(self.session,force=True)
        before = mailbox_extras.status(self.path,1,1001,now=200)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO native_relationship_mail VALUES('owned-move',2,1001,'owned-pair',NULL,22,1,1)")
        self.assertEqual(mailbox_extras.status(self.path,1,1001,now=200),before)
        self.session.mailbox_poll = (None,0)
        result = mail_flow.periodic(self.session)
        self.assertEqual(len(result),1)
        self.assertEqual(unread_counts(result[0]),{0:1,1:0,2:2,3:1,4:0})

    def test_last_unread_becoming_read_clears_every_count(self):
        mail_flow.periodic(self.session,force=True)
        for mid in (1,2,3,4):
            game_mail.read(self.path,1,1001,mid,lambda row: row['id'],now=200)
        self.session.mailbox_poll = (None,0)
        self.assertEqual(unread_counts(mail_flow.periodic(self.session)[0]),dict.fromkeys(range(5),0))

    def test_unchanged_counts_suppress_duplicates_but_force_resends(self):
        first = mail_flow.periodic(self.session,force=True)
        self.session.mailbox_poll = (None,0)
        self.assertEqual(mail_flow.periodic(self.session),[])
        self.assertEqual(mail_flow.periodic(self.session,force=True),first)

    def test_character_switch_cannot_receive_sibling_letters(self):
        mail_flow.periodic(self.session,force=True)
        self.session.account.uid = 1002
        result = mail_flow.periodic(self.session)
        self.assertEqual(unread_counts(result[0]),{0:0,1:1,2:0,3:0,4:0})
        self.assertEqual(self.snapshot(uid=1002)['visible_unread_ids'],(5,))

    def test_wrong_account_is_rejected(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN')
            with self.assertRaises(game_mail.MailError):
                online_2026_mail_snapshot.snapshot(db,account=3,character=1001,now=200)

    def test_shared_reward_notice_preserves_other_folders(self):
        state = self.snapshot()
        event = notice(unread_counts=state['unread_counts'],rows=[],flag=False)
        self.assertEqual(unread_counts(event),{0:1,1:1,2:1,3:1,4:0})

    def test_legacy_mail_without_optional_ledgers_still_routes_system_and_normal(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            for table in ('native_relationship_mail','native_guild_reward_mail_v2','online2026_mail_scope'):
                db.execute('DROP TABLE '+table)
        state = self.snapshot()
        self.assertEqual(state['unread_counts'],{0:3,1:1,2:0,3:0,4:0})
        self.assertEqual(state['activity_unread_ids'],())
