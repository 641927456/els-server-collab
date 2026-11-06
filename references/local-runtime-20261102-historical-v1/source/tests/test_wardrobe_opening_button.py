"""The original wardrobe button sends 51C from one zero performer."""
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch
import os,sqlite3,tempfile,struct,unittest

from els_server.domain import avatar_set_flow
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.protocol.protocol_codec import (
    BOOTSTRAP_KEYS,Event,decode_event,decode_frame,encode_event,encode_frame,
)
from els_server.protocol.wardrobe_messages import opening_request
from els_server.storage import wardrobe
from els_server.storage.local_state import LocalState


class WardrobeOpeningButtonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        uid=self.account.characters.create('OpeningOther',5,'other')['uid']
        self.account.for_character(uid)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE reward_balances SET ed=1000')
        self.session=LocalSession(self.account,enter_town=True,enter_dungeon=True,npc_slot_test=True,
            gate_test=True,population_test=True,clear_test=True,reward_test=True,
            item_test=True,shop_test=True,client_build='dx11_260923')
        self.session.role,self.session.phase='game','town_ready'
        self.response=Event(0x201,kind=0x51d,payload=bytes(32))
        self.opening=Mock(return_value=[self.response])
        self.context=Mock(return_value=object())
        self.validate=Mock()
        self.enterContext(patch.object(avatar_set_flow,'context',self.context))
        self.enterContext(patch.object(avatar_set_flow,'validate',self.validate))
        self.enterContext(patch.object(wardrobe,'opening_info',self.opening))

    def frame(self,payload,performers=(0,)):
        return encode_frame(encode_event(Event(0x202,kind=0x51c,performers=performers,payload=payload)),BOOTSTRAP_KEYS)

    def deliver(self,wire,sequence=1):
        return self.session.handle(decode_event(decode_frame(wire,BOOTSTRAP_KEYS).plaintext),sequence)

    def test_native_frame_is_eighty_eight_bytes_and_opens_the_wardrobe(self):
        # The fixed DX11 capture logs this request at 88 wire bytes, which only
        # a zero performer plus a widened house/selector pair can produce.
        wire=self.frame(struct.pack('>qq',0,3))
        self.assertEqual(len(wire),88)
        self.assertEqual(self.deliver(wire),[self.response])
        self.opening.assert_called_once()
        owner,uid,account_id=self.opening.call_args.args
        self.assertTrue(os.path.samefile(owner,self.path))
        self.assertEqual((uid,account_id),(1001,1))
        self.assertTrue(callable(self.opening.call_args.kwargs['validate']))

    def test_narrow_pair_and_padded_pair_are_the_same_request(self):
        for payload in (struct.pack('>ii',0,3),struct.pack('>qq',0,3),
                        struct.pack('>ii',0,3)+b'\x00',struct.pack('>ii',0,3)+bytes(8)):
            with self.subTest(size=len(payload)):
                self.assertEqual(opening_request(payload),(0,3))

    def test_legacy_empty_performer_fixture_still_opens(self):
        self.assertEqual(self.deliver(self.frame(struct.pack('>qq',0,3),performers=())),[self.response])

    def test_foreign_envelopes_and_pairs_never_reach_storage(self):
        self.assertEqual(self.deliver(self.frame(struct.pack('>qq',0,3),performers=(0,1))),[])
        for payload in (struct.pack('>qq',0,4),struct.pack('>qq',1,3),struct.pack('>ii',0,3)[:4],b''):
            with self.subTest(payload=payload):
                self.assertRaises(ValueError,opening_request,payload)
                self.assertEqual(self.deliver(self.frame(payload)),[])
        for sequence in (0,2**32,True,None):
            with self.subTest(sequence=sequence):
                self.assertEqual(self.deliver(self.frame(struct.pack('>qq',0,3)),sequence),[])
        self.session.phase='dungeon_active'
        self.assertEqual(self.deliver(self.frame(struct.pack('>qq',0,3))),[])
        self.opening.assert_not_called()
