"""Portable chip failure/namespace/routing checks; no DB, resources or game."""
import struct
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.equipment_chip_flow import handle
from els_server.protocol.equipment_chip_messages import reset_unavailable_ack
from els_server.protocol.protocol_codec import Event, decode_event, encode_event


class NoStateAccess:
    client_build='dx11_260923'
    def __getattr__(self,name):
        raise AssertionError('Unexpected state access: '+name)


class ChipFailure(unittest.TestCase):
    def test_complete_failure_body_and_codec(self):
        ack=reset_unavailable_ack()
        self.assertEqual((ack.event_id,ack.kind),(0x201,0xbbd))
        self.assertEqual(ack.payload,struct.pack('>iI',2005,0))
        self.assertEqual(decode_event(encode_event(ack)),ack)

    def test_failure_needs_no_payload_or_player_state(self):
        # Failure-only handling deliberately does not parse the unresolved
        # reset transaction or inspect phase, role, switches or account.
        for body in (None,b'',b'bad',bytes(16),bytes([255])*16):
            with self.subTest(body=body):
                ack=handle(NoStateAccess(),Event(0x202,kind=0xbbc,payload=body),None)
                self.assertEqual(ack,[reset_unavailable_ack()])

    def test_other_namespace_or_build_is_not_admitted(self):
        self.assertIsNone(handle(NoStateAccess(),Event(0x201,kind=0xbbc),1))
        wrong=types.SimpleNamespace(client_build='other',item_test=True)
        self.assertIsNone(handle(wrong,Event(0x202,kind=0xbbc),1))
        off=types.SimpleNamespace(client_build='dx11_260923',item_test=False)
        self.assertIsNone(handle(off,Event(0x202,kind=0xbb8),1))

    def test_existing_bb8_routes_to_existing_transaction(self):
        account=types.SimpleNamespace(uid=1001,characters=object(),
            store=types.SimpleNamespace(path='unused-private-fixture'),
            get_reward_balances=Mock(return_value={'ed':0}))
        session=types.SimpleNamespace(client_build='dx11_260923',item_test=True,
            role='game',phase='town_ready',account=account,shop_session_id='fixture-session')
        request=Event(0x202,kind=0xbb8,payload=struct.pack('>Qi',123,0))
        sentinel=[Event(0x201,kind=0xbb9,payload=b'fixture')]
        transaction=Mock(return_value=sentinel)
        storage=types.ModuleType('els_server.storage.equipment_chip')
        storage.perform=transaction
        with patch.dict(sys.modules,{'els_server.storage.equipment_chip':storage}):
            self.assertEqual(handle(session,request,7),sentinel)
        transaction.assert_called_once_with('unused-private-fixture',1001,request.payload,
            'fixture-session:chip-compat-v1:1001:7',install=False)


if __name__=='__main__':
    unittest.main(verbosity=2)
