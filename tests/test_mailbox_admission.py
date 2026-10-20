"""Source-only mailbox regressions; no runtime assets, database or socket use."""
from dataclasses import dataclass
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.friends_world import Mailbox,FriendsWorld
from els_server.domain.local_session import SessionOrderError

@dataclass(eq=False)
class Message:
    payload:bytes

def state(box):
    return tuple(id(row) for row in box.messages),tuple((key,id(row)) for key,row in box.moves.items()),box.bytes

class MailboxAdmissionTests(unittest.TestCase):
    def test_mixed_capacity_counts_replacement_once_and_preserves_fifo(self):
        box=Mailbox();ordered=[Message(b'c') for _ in range(129)]
        for row in ordered:box.append(row)
        for uid in range(127):box.append(Message(b'm'),uid)
        replacement=Message(b'r'*64);box.append(replacement,0)
        self.assertEqual(box.bytes,319);self.assertEqual(len(box.messages)+len(box.moves),256)
        before=state(box)
        with self.assertRaises(SessionOrderError):box.append(Message(b'new'),127)
        self.assertEqual(state(box),before);self.assertIs(box.moves[0],replacement)
        result=box.drain();self.assertEqual(result[:129],ordered);self.assertIs(result[129],replacement)
        self.assertEqual(state(box),((),(),0))

    def test_exact_byte_capacity_keeps_failed_replacements_and_supports_shrink(self):
        box=Mailbox();chunks=[Message(b'b'*65536) for _ in range(4)]
        for uid,row in enumerate(chunks):box.append(row,uid)
        before=state(box)
        for key in (None,4):
            with self.subTest(key=key):
                with self.assertRaises(SessionOrderError):box.append(Message(b'!'),key)
                self.assertEqual(state(box),before)
        with self.assertRaises(SessionOrderError):box.append(Message(b'x'*65537),2)
        self.assertEqual(state(box),before);self.assertIs(box.moves[2],chunks[2])
        box.append(Message(b''),2);self.assertEqual(box.bytes,3*65536)
        box.append(Message(b'n'*65536));self.assertEqual(box.bytes,256*1024)

    def test_oversized_first_message_never_enters_a_queue(self):
        for key in (None,0):
            box=Mailbox()
            with self.assertRaises(SessionOrderError):box.append(Message(b'x'*(256*1024+1)),key)
            self.assertEqual(state(box),((),(),0))

    def test_terminal_consumer_rejects_further_sends_without_harming_peer(self):
        world=FriendsWorld.__new__(FriendsWorld)
        slow=SimpleNamespace(released=False,social_overflow=False,mailbox=Mailbox())
        peer=SimpleNamespace(released=False,social_overflow=False,mailbox=Mailbox())
        for _ in range(256):world.send(slow,Message(b''))
        frozen=state(slow.mailbox);world.send(slow,Message(b'rejected'))
        self.assertTrue(slow.social_overflow);self.assertEqual(state(slow.mailbox),frozen)
        for _ in range(100):world.send(slow,Message(b'ignored'),0)
        self.assertEqual(state(slow.mailbox),frozen)
        healthy=Message(b'healthy');world.send(peer,healthy)
        self.assertEqual(peer.mailbox.drain(),[healthy]);self.assertFalse(peer.social_overflow)
        slow.mailbox.drain();world.send(slow,Message(b'still terminal'))
        self.assertTrue(slow.social_overflow);self.assertEqual(state(slow.mailbox),((),(),0))

    def test_released_session_send_leaves_existing_queue_unchanged(self):
        world=FriendsWorld.__new__(FriendsWorld);box=Mailbox();box.append(Message(b'prior'))
        session=SimpleNamespace(released=True,social_overflow=False,mailbox=box);before=state(box)
        world.send(session,Message(b'new'));self.assertEqual(state(box),before)

if __name__=='__main__':unittest.main(verbosity=2)
