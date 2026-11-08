"""Offline guild-chat and deleted-sender return-mail regressions."""
from collections import deque
from contextlib import closing
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
from els_server.domain.friends_world import FriendsWorld, Mailbox
from els_server.domain.guild_license_flow import reply_capture
from els_server.protocol import social_messages
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event
from els_server.storage import character_lifecycle, game_mail, guild_membership_state
from els_server.storage import inventory_state, item_instances, mailbox_extras, player_mail


class Fixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='owned-offline-',dir=WORK)
        self.path = Path(self.directory.name)/'fixture.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''CREATE TABLE characters(uid INTEGER PRIMARY KEY,name TEXT,
                name_key TEXT,unit_type INTEGER,unit_class INTEGER,level INTEGER,
                revision INTEGER NOT NULL DEFAULT 0)''')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER)')
            db.executemany('INSERT INTO characters VALUES(?,?,?,1,1,99,0)',
                ((1001,'Sender','sender'),(1002,'Sibling','sibling'),
                 (1003,'Recipient','recipient'),(1004,'Stranger','stranger')))
            db.executemany('INSERT INTO character_owners VALUES(?,?)',
                           ((1001,1),(1002,1),(1003,2),(1004,3)))

    def tearDown(self):
        self.directory.cleanup()

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return tuple(db.iterdump())


class Registry:
    def __init__(self,path):
        self.path = path
        self.disabled = set()

    def enabled(self,account):
        return account not in self.disabled


class ChatPeer:
    def __init__(self,app,uid,account_id,name):
        store = SimpleNamespace(uid=uid,path=app.config.state_file)
        characters = SimpleNamespace(path=store.path,account_id=account_id)
        root = SimpleNamespace(characters=characters,account_id=account_id,store=store,
                               character_accounts={})
        root.root = root
        account = SimpleNamespace(uid=uid,account_id=account_id,store=store,characters=characters,root=root,
            character=lambda:dict(uid=uid,name=name),get_location=lambda:dict(map=20000))
        root.character_accounts[uid] = account
        self.application,self.account = app,account
        self.identity = dict(id=account_id)
        self.role,self.phase,self.client_build = 'game','town_ready','dx11_260923'
        self.item_test,self.enter_town = True,True
        self.released,self.dungeon_return_pending = False,False
        self.shop_session_id = 'owned-chat-'+str(uid)
        self.active_map,self.pending_map,self.dungeon_id = 20000,20000,0
        self.completed,self.dungeon_run = {0x28},None
        self.mailbox,self.chat_times = Mailbox(),deque()
        app.playing[account_id],app.accounts[account_id] = self,root


def chat_event():
    payload = bytes((3,0))+struct.pack('>Q',2**64-1)
    payload += wstring('')+wstring('离线公会聊天')+wstring('')
    payload += struct.pack('>iQBiQiI',-1,2**64-1,0,0,0,0,0)
    return Event(0x202,kind=0x85,payload=payload)


class GuildChat(Fixture):
    def setUp(self):
        super().setUp()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE character_owners SET account_id=4 WHERE uid=1002')
            guild_membership_state._schema(db)
            db.execute("INSERT INTO native_guilds VALUES(1,'OwnedGuild','ownedguild',1001,1,'',1,1)")
            for uid,account,grade in ((1001,1,1),(1002,4,6)):
                operation = 'owned-guild-'+str(uid)
                db.execute('INSERT INTO native_guild_members VALUES(?,?,1,?,1,?)',(uid,account,grade,operation))
                db.execute('INSERT INTO native_guild_actions VALUES(?,?,?, ?,1,1)',
                           (operation,'0'*64,uid,0x276 if grade==1 else 0x288))
        self.world = SimpleNamespace(dungeons=SimpleNamespace(room=lambda s:None),members={},towns={})
        self.app = SimpleNamespace(world=self.world,config=SimpleNamespace(state_file=self.path),
            accounts={},playing={},registry=Registry(self.path))
        self.sender = ChatPeer(self.app,1001,1,'Sender')
        self.target = ChatPeer(self.app,1002,4,'Sibling')
        self.stranger = ChatPeer(self.app,1003,2,'Recipient')
        self.assertIsNotNone(reply_capture(self.sender))
        self.assertIsNotNone(reply_capture(self.target))

    def chat(self):
        return FriendsWorld.chat(self.world,self.sender,chat_event())

    def test_all_five_current_chat_scenes_receive_guild_messages(self):
        phases = ('town_ready','dungeon_active','guild_agit_ready','photo_zone_admitted','wedding_hall')
        for source in phases:
            for destination in phases:
                with self.subTest(source=source,destination=destination):
                    self.sender.phase,self.target.phase = source,destination
                    self.sender.chat_times.clear()
                    result = self.chat()
                    self.assertEqual(result,[social_messages.chat_ack()])
                    expected = social_messages.chat_notice(self.sender.account.character(),1,'离线公会聊天',3)
                    self.assertEqual(self.sender.mailbox.drain(),[expected])
                    self.assertEqual(self.target.mailbox.drain(),[expected])
                    self.assertEqual(self.stranger.mailbox.drain(),[])

    def test_unavailable_or_foreign_actor_receives_nothing(self):
        for phase in ('closing','map_loading','channels_ready'):
            with self.subTest(phase=phase):
                self.target.phase = phase
                self.sender.chat_times.clear()
                self.assertEqual(self.chat(),[social_messages.chat_ack()])
                self.assertEqual(self.target.mailbox.drain(),[])
                self.sender.mailbox.drain()
        self.target.phase = 'wedding_hall'
        for mode in ('disabled','replaced','foreign-database'):
            with self.subTest(mode=mode):
                self.sender.chat_times.clear()
                old_path = self.target.account.store.path
                if mode=='disabled':self.app.registry.disabled.add(4)
                if mode=='replaced':self.app.playing[4] = self.stranger
                if mode=='foreign-database':self.target.account.store.path = self.path.with_name('foreign.sqlite3')
                self.assertEqual(self.chat(),[social_messages.chat_ack()])
                self.assertEqual(self.target.mailbox.drain(),[])
                self.sender.mailbox.drain()
                self.app.registry.disabled.clear()
                self.app.playing[4] = self.target
                self.target.account.store.path = old_path

    def test_full_wedding_recipient_queue_rejects_without_partial_send(self):
        self.target.phase = 'wedding_hall'
        existing = Event(0x201,kind=0x87,payload=b'old')
        for _ in range(256):self.target.mailbox.append(existing)
        before = tuple(self.target.mailbox.messages)
        self.assertEqual(self.chat(),[social_messages.chat_ack(1)])
        self.assertEqual(tuple(self.target.mailbox.messages),before)
        self.assertEqual(self.sender.mailbox.drain(),[])
        self.assertEqual(self.sender.chat_times,deque())

    def test_invalid_membership_receipt_rejects_without_delivery(self):
        self.target.phase = 'wedding_hall'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM native_guild_actions WHERE owner=1002')
        self.assertEqual(self.chat(),[social_messages.chat_ack(1)])
        self.assertEqual(self.sender.mailbox.drain(),[])
        self.assertEqual(self.target.mailbox.drain(),[])


class ReturnedMail(Fixture):
    NOW = 100
    EXPIRED = NOW + player_mail.ORDINARY_RETENTION

    def setUp(self):
        super().setUp()
        with closing(sqlite3.connect(self.path)) as db, db:
            game_mail.ensure(db)
            inventory_state.ensure_inventory(db)
            db.execute('CREATE TABLE reward_balances(uid INTEGER PRIMARY KEY,ed INTEGER,experience INTEGER,revision INTEGER)')
            db.executemany('INSERT INTO reward_balances VALUES(?,10000,0,0)',((uid,) for uid in range(1001,1005)))

    def send(self,item=None):
        if item is not None:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN')
                item_instances.insert(db,1001,item)
        request = dict(recipient='Recipient',title='Owned mail',body='Offline fixture',
                       ed=500 if item is None else 0,
                       item=0 if item is None else item['uid'],
                       count=0 if item is None else item['count'],flag=0,extra=0)
        return player_mail.send(self.path,1,1001,request,'owned-original-send',lambda row:row,now=self.NOW)['mail_id']

    def pending_sender(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            character_lifecycle.initialize(db)
            db.execute('''INSERT INTO character_lifecycle
                (uid,account_id,created_at,requested_at,finalize_at,restore_at)
                VALUES(1001,1,1,200,300,250)''')

    def finalize_sender(self):
        self.pending_sender()
        with patch.object(character_lifecycle,'current_time',return_value=400):
            character_lifecycle.change(self.path,1,1001,'finalize')

    def returned(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT mail_id,recipient_uid FROM player_mail_meta WHERE return_of IS NOT NULL').fetchone()

    def historical_return(self,*,item=False):
        payload = dict(uid=9000001,template=77000,metadata=2,count=3,group=6,slot=0) if item else None
        mid = self.send(payload)
        self.assertEqual(player_mail.maintenance(self.path,now=self.EXPIRED),1)
        returned,target = self.returned()
        self.assertEqual(target,1001)
        self.finalize_sender()
        return mid,returned

    def claim(self,mid,uid=1002):
        return game_mail.claim(self.path,1,uid,[mid],lambda ids,ed:(ids,ed),now=self.EXPIRED+1)

    def test_new_return_after_finalization_is_account_owned_and_claimed_once(self):
        original = self.send()
        self.finalize_sender()
        self.assertEqual(player_mail.maintenance(self.path,now=self.EXPIRED),1)
        returned,target = self.returned()
        self.assertEqual(target,0)
        self.assertEqual([r['id'] for r in game_mail.inbox(self.path,1,1002,now=self.EXPIRED)[1]],[returned])
        self.assertEqual(self.claim(returned),([returned],10500))
        self.assertEqual(self.claim(returned),([returned],10500))
        self.assertEqual(player_mail.maintenance(self.path,now=self.EXPIRED+2),0)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM game_mail WHERE campaign=?',('player-return-'+str(original),)).fetchone()[0],1)

    def test_historical_return_becomes_visible_without_rewriting_metadata(self):
        _,returned = self.historical_return()
        with closing(sqlite3.connect(self.path)) as db:
            before = db.execute('SELECT * FROM player_mail_meta').fetchall()
        self.assertEqual(mailbox_extras.status(self.path,1,1002,now=self.EXPIRED),(1,1,returned))
        self.assertEqual(game_mail.inbox(self.path,1,1002,folder=1,now=self.EXPIRED)[0],1)
        self.assertEqual(game_mail.read(self.path,1,1002,returned,lambda row:row['id'],now=self.EXPIRED),returned)
        self.assertEqual(self.claim(returned)[1],10500)
        self.assertEqual(game_mail.delete(self.path,1,1002,[returned],lambda ids:ids,now=self.EXPIRED+2),[returned])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM player_mail_meta').fetchall(),before)

    def test_pending_sender_keeps_character_scope_until_restore(self):
        self.send()
        self.pending_sender()
        player_mail.maintenance(self.path,now=self.EXPIRED)
        returned,target = self.returned()
        self.assertEqual(target,1001)
        self.assertEqual(game_mail.inbox(self.path,1,1002,now=self.EXPIRED)[0],0)
        with self.assertRaises(game_mail.MailError):self.claim(returned)
        with patch.object(character_lifecycle,'current_time',return_value=400):
            character_lifecycle.change(self.path,1,1001,'restore')
        self.assertEqual(self.claim(returned,uid=1001)[1],9775)

    def test_legacy_sender_without_lifecycle_keeps_character_scope(self):
        self.send()
        player_mail.maintenance(self.path,now=self.EXPIRED)
        returned,target = self.returned()
        self.assertEqual(target,1001)
        self.assertEqual(game_mail.inbox(self.path,1,1002,now=self.EXPIRED)[0],0)
        with self.assertRaises(game_mail.MailError):self.claim(returned)
        self.assertEqual(self.claim(returned,uid=1001)[1],9775)

    def test_account_guard_and_nonreturn_recipient_scope_are_preserved(self):
        original,returned = self.historical_return()
        with self.assertRaises(game_mail.MailError):
            game_mail.read(self.path,3,1004,returned,lambda row:row,now=self.EXPIRED)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at)
                VALUES('owned-inbound',1,'Other','Title','Body',250,100,?)''',(self.EXPIRED+100,))
            inbound = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute('INSERT INTO player_mail_meta VALUES(?,1001,2,1003,NULL,NULL)',(inbound,))
        self.assertEqual([r['id'] for r in game_mail.inbox(self.path,1,1002,now=self.EXPIRED)[1]],[returned])
        with self.assertRaises(game_mail.MailError):self.claim(inbound)

    def test_mismatched_tombstone_account_does_not_expand_scope(self):
        _,returned = self.historical_return()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE character_lifecycle SET account_id=3 WHERE uid=1001')
        self.assertEqual(game_mail.inbox(self.path,1,1002,now=self.EXPIRED)[0],0)
        with self.assertRaises(game_mail.MailError):self.claim(returned)

    def test_historical_attachment_claim_rollback_and_replay_preserve_one_item(self):
        _,returned = self.historical_return(item=True)
        before = self.dump()
        def reject(*args):raise RuntimeError('Owned encoding failure')
        with self.assertRaisesRegex(RuntimeError,'Owned encoding failure'):
            game_mail.claim(self.path,1,1002,[returned],reject,include_items=True,now=self.EXPIRED+1)
        self.assertEqual(self.dump(),before)
        encode = lambda ids,ed,changes:(ids,ed,changes)
        first = game_mail.claim(self.path,1,1002,[returned],encode,include_items=True,now=self.EXPIRED+1)
        second = game_mail.claim(self.path,1,1002,[returned],encode,include_items=True,now=self.EXPIRED+2)
        self.assertEqual(first,second)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT uid,owner,count FROM inventory_items').fetchall(),[(9000001,1002,3)])

    def test_return_creation_failure_rolls_back_and_retry_creates_one_return(self):
        self.send()
        self.finalize_sender()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''CREATE TRIGGER owned_return_failure BEFORE UPDATE OF returned_to ON player_mail_meta
                BEGIN SELECT RAISE(ABORT,'owned return failure'); END''')
        before = self.dump()
        with self.assertRaisesRegex(sqlite3.IntegrityError,'owned return failure'):
            player_mail.maintenance(self.path,now=self.EXPIRED)
        self.assertEqual(self.dump(),before)
        with closing(sqlite3.connect(self.path)) as db, db:db.execute('DROP TRIGGER owned_return_failure')
        player_mail.maintenance(self.path,now=self.EXPIRED)
        self.assertEqual(self.returned()[1],0)
        self.assertEqual(player_mail.maintenance(self.path,now=self.EXPIRED+1),0)

    def test_new_attachment_return_keeps_uid_and_quantity(self):
        item = dict(uid=9000002,template=77000,metadata=2,count=7,group=6,slot=0)
        original = self.send(item)
        self.finalize_sender()
        player_mail.maintenance(self.path,now=self.EXPIRED)
        returned,target = self.returned()
        self.assertEqual(target,0)
        game_mail.claim(self.path,1,1002,[returned],lambda *args:args,include_items=True,now=self.EXPIRED+1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT uid,owner,count FROM inventory_items').fetchall(),[(9000002,1002,7)])
            self.assertEqual(db.execute('SELECT moved_to FROM player_mail_items WHERE mail_id=?',(original,)).fetchone(),(returned,))
