"""Offline regressions through existing chat and blacklist entry points."""
from collections import deque
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import json
import sqlite3
import struct
import sys
import tempfile
import unittest

import bootstrap
WORK = bootstrap.WORK
from els_server.domain.friends_world import FriendsWorld, Mailbox
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.protocol import social_messages
from els_server.storage import mailbox_extras, character_lifecycle


class ChatPeer:
    def __init__(self, application, account, uid, name, phase):
        self.application = application
        self.identity = dict(id=account)
        self.account = SimpleNamespace(
            uid=uid, character=lambda: dict(uid=uid, name=name),
        )
        self.phase = phase
        self.released = False
        self.role = 'game'
        self.coop_error = None
        self.mailbox = Mailbox()
        self.chat_times = deque()


def whisper_event(recipient, target=2**64 - 1):
    payload = bytes((4, 0)) + struct.pack('>Q', target)
    payload += wstring(recipient) + wstring('测试私聊') + wstring('')
    payload += struct.pack('>iQBiQiI', 0, 2**64 - 1, 0, 0, 0, 0, 0)
    return Event(0x202, kind=0x85, payload=payload)


class WhisperRouting(unittest.TestCase):
    def peers(self, target_phase):
        application = SimpleNamespace(
            playing={}, registry=SimpleNamespace(enabled=lambda account: True),
        )
        sender = ChatPeer(application, 1, 1001, 'Sender', 'town_ready')
        target = ChatPeer(application, 2, 1002, 'Recipient', target_phase)
        application.playing.update({1: sender, 2: target})
        return SimpleNamespace(), sender, target

    def test_all_current_chat_scenes_receive_whispers(self):
        phases = ('town_ready', 'dungeon_active', 'photo_zone_admitted',
                  'guild_agit_ready', 'wedding_hall')
        for sender_phase in phases:
            for target_phase in phases:
                with self.subTest(sender_phase=sender_phase, target_phase=target_phase):
                    world, sender, target = self.peers(target_phase)
                    sender.phase = sender_phase
                    result = FriendsWorld.chat(world, sender, whisper_event('Recipient'))
                    self.assertEqual(result[0].payload, bytes(4))
                    expected = social_messages.chat_notice(
                        sender.account.character(), 1, '测试私聊', 4,
                        recipient=target.account.character(),
                    )
                    self.assertEqual(sender.mailbox.drain(), [expected])
                    self.assertEqual(target.mailbox.drain(), [expected])

    def test_unavailable_target_and_mismatched_uid_receive_nothing(self):
        for phase, target_uid in (('closing', 1002), ('map_loading', 1002),
                                  ('town_ready', 9999)):
            with self.subTest(phase=phase, target_uid=target_uid):
                world, sender, target = self.peers(phase)
                result = FriendsWorld.chat(world, sender, whisper_event('Recipient', target_uid))
                self.assertEqual(result[0].payload, struct.pack('>i', 1))
                self.assertEqual(target.mailbox.drain(), [])

    def test_full_recipient_mailbox_preserves_both_queues(self):
        world, sender, target = self.peers('guild_agit_ready')
        existing = Event(0x201, kind=0x87, payload=b'old')
        for _ in range(256):
            target.mailbox.append(existing)
        before = tuple(target.mailbox.messages)
        with self.assertRaises(ValueError):
            FriendsWorld.chat(world, sender, whisper_event('Recipient'))
        self.assertEqual(tuple(target.mailbox.messages), before)
        self.assertEqual(sender.mailbox.drain(), [])
        self.assertEqual(sender.chat_times, deque())


class BlacklistLifecycle(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='owned-social-', dir=WORK)
        self.path = Path(self.directory.name) / 'fixture.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY, name TEXT, name_key TEXT)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY, account_id INTEGER)')
            db.executemany('INSERT INTO characters VALUES(?,?,?)', (
                (1001, 'Sender', 'sender'), (1002, 'Recipient', 'recipient'),
                (1003, 'Pending', 'pending'), (1004, 'Deleted', ':deleted:1004'),
            ))
            db.executemany('INSERT INTO character_owners VALUES(?,?)', ((1001,1),(1002,2),(1003,3),(1004,4)))
            mailbox_extras.ensure(db)

    def tearDown(self):
        self.directory.cleanup()

    def lifecycle(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            character_lifecycle.initialize(db)
            db.execute('INSERT INTO character_lifecycle(uid,account_id,created_at,requested_at) VALUES(1003,3,1,10)')
            db.execute('INSERT INTO character_lifecycle(uid,account_id,created_at,requested_at,finalized_at) VALUES(1004,4,1,10,20)')

    def test_deleted_and_missing_characters_leave_visible_blacklist(self):
        self.lifecycle()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('INSERT INTO mail_blacklist VALUES(?,?,?,?)', (
                (1001,1002,'OldRecipientName',1), (1001,1003,'Pending',2),
                (1001,1004,'Deleted',3), (1001,9999,'Missing',4),
            ))
        self.assertEqual(mailbox_extras.blacklist(self.path,1,1001), [
            dict(uid=1002,name='Recipient'), dict(uid=1003,name='Pending'),
        ])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_blacklist').fetchone()[0],4)

    def test_legacy_database_without_lifecycle_keeps_live_names(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO mail_blacklist VALUES(1001,1002,?,1)', ('OldName',))
        self.assertEqual(mailbox_extras.blacklist(self.path,1,1001), [dict(uid=1002,name='Recipient')])

    def test_removing_deleted_entry_is_idempotent_and_receipt_is_retained(self):
        self.lifecycle()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO mail_blacklist VALUES(1001,1004,?,1)', ('Deleted',))
        encode = lambda row,result,rows: dict(row=row,result=result,rows=rows)
        first = mailbox_extras.change(self.path,1,1001,1004,added=False,
                                       operation='owned-remove',encode=encode,now=30)
        second = mailbox_extras.change(self.path,1,1001,1004,added=False,
                                        operation='owned-remove',encode=encode,now=31)
        self.assertEqual(first,second)
        self.assertEqual(first['rows'],[])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_blacklist_receipts').fetchone()[0],1)

    def test_deleted_entries_do_not_consume_live_blacklist_capacity(self):
        self.lifecycle()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('INSERT INTO mail_blacklist VALUES(?,?,?,1)', (
                (1001,uid,'Missing') for uid in range(2000,3000)
            ))
        result = mailbox_extras.change(
            self.path,1,1001,'Recipient',added=True,operation='owned-add-live',
            encode=lambda row,result,rows: (result,rows),now=30,
        )
        self.assertEqual(result,(0,[dict(uid=1002,name='Recipient')]))

    def test_full_live_blacklist_still_rejects_new_entry(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany('INSERT INTO characters VALUES(?,?,?)', (
                (uid,'Live'+str(uid),'live'+str(uid)) for uid in range(2000,3000)
            ))
            db.executemany('INSERT INTO mail_blacklist VALUES(?,?,?,1)', (
                (1001,uid,'Live'+str(uid)) for uid in range(2000,3000)
            ))
        with self.assertRaisesRegex(ValueError,'Blacklist storage bound'):
            mailbox_extras.change(
                self.path,1,1001,'Recipient',added=True,operation='owned-full',
                encode=lambda *args: args,now=30,
            )
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_blacklist').fetchone()[0],1000)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_blacklist_receipts').fetchone()[0],0)

    def test_old_add_retry_after_deletion_does_not_reappear_or_rewrite_receipt(self):
        encode = lambda row,result,rows: dict(result=result,rows=rows)
        first = mailbox_extras.change(self.path,1,1001,'Recipient',added=True,
                                      operation='owned-add-retry',encode=encode,now=5)
        self.assertEqual(first['result'],0)
        with closing(sqlite3.connect(self.path)) as db, db:
            character_lifecycle.initialize(db)
            db.execute('INSERT INTO character_lifecycle(uid,account_id,created_at,finalized_at) VALUES(1002,2,1,10)')
            db.execute("UPDATE characters SET name_key=':deleted:1002' WHERE uid=1002")
            receipt = db.execute('SELECT * FROM mail_blacklist_receipts').fetchall()
        replay = mailbox_extras.change(self.path,1,1001,'Recipient',added=True,
                                       operation='owned-add-retry',encode=encode,now=20)
        self.assertEqual(replay,dict(result=1,rows=[]))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM mail_blacklist_receipts').fetchall(),receipt)

    def test_failed_encoding_rolls_back_new_entry_and_receipt(self):
        def fail_encoding(*args):
            raise RuntimeError('owned encoding failure')
        with self.assertRaisesRegex(RuntimeError,'owned encoding failure'):
            mailbox_extras.change(self.path,1,1001,'Recipient',added=True,
                                   operation='owned-failed-encoding',encode=fail_encoding,now=5)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_blacklist').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM mail_blacklist_receipts').fetchone()[0],0)
