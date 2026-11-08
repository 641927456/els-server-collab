"""Regression proof for findings from the integrated source review."""
from contextlib import closing
import sqlite3
import threading
from unittest.mock import patch

from test_social_basics import WhisperRouting, whisper_event
from test_friend_mail import MailFolders, unread_counts, mail_flow
from test_guild_returns import ReturnedMail
from els_server.domain import party_commands
from els_server.domain.friends_world import FriendsWorld
from els_server.protocol.mail_notifications_2026 import notice
from els_server.protocol.protocol_codec import Event
from els_server.storage import game_mail


class ReviewWhisper(WhisperRouting):
    def test_whisper_keeps_concurrent_recipient_message(self):
        world,sender,target = self.peers('wedding_hall')
        target.social_overflow = False
        concurrent = Event(0x201,kind=0x87,payload=b'concurrent fixture')
        original = party_commands._prepared_boxes
        attempted = threading.Event()
        threads = []

        def prepare(deliveries,response):
            planned = original(deliveries,response)

            def append_to_current_box():
                lock = target.mailbox.lock
                if lock.acquire(blocking=False):
                    try: FriendsWorld.send(world,target,concurrent)
                    finally: lock.release()
                    attempted.set()
                else:
                    attempted.set()
                    FriendsWorld.send(world,target,concurrent)

            thread = threading.Thread(target=append_to_current_box)
            threads.append(thread);thread.start()
            self.assertTrue(attempted.wait(3),'Recipient writer did not reach the mailbox')
            return planned

        with patch.object(party_commands,'_prepared_boxes',side_effect=prepare):
            response = FriendsWorld.chat(world,sender,whisper_event('Recipient'))
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive(),'Recipient writer did not finish')
        self.assertEqual(response[0].payload,bytes(4))
        echoed = sender.mailbox.drain()
        self.assertEqual(len(echoed),1)
        self.assertEqual(target.mailbox.drain(),echoed+[concurrent])


class ReviewMailStatus(MailFolders):
    def test_read_reward_with_same_unread_totals_sends_corrected_notice(self):
        initial = mail_flow.periodic(self.session,force=True)[0]
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('''INSERT INTO game_mail
                (id,campaign,account_id,sender,title,body,ed,created_at,expires_at)
                VALUES(10,'owned-immediate-reward',1,'Reward','Title','Body',0,150,1000)''')
        # The reward producer sends its own 1CE after the escrow commits.
        immediate = notice(unread_counts=self.snapshot()['unread_counts'],rows=(),flag=False)
        self.assertEqual(unread_counts(immediate)[0],unread_counts(initial)[0]+1)
        game_mail.read(self.path,1,1001,10,lambda row:row['id'],now=200)
        self.session.mailbox_poll = (None,0)
        updated = mail_flow.periodic(self.session)
        self.assertEqual(updated,[initial])


class ReviewReturns(ReturnedMail):
    def test_predeletion_claim_cannot_be_reclaimed_by_sibling(self):
        self.send()
        from els_server.storage import player_mail
        player_mail.maintenance(self.path,now=self.EXPIRED)
        returned,_ = self.returned()
        self.assertEqual(self.claim(returned,uid=1001)[1],9775)
        self.finalize_sender()
        before = self.dump()
        self.assertEqual(self.claim(returned,uid=1002)[1],10000)
        self.assertEqual(self.dump(),before)
