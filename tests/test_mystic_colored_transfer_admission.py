"""Portable admission tests; artifact TLS covers real economic state/codec."""
import struct,sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from els_server.protocol.protocol_codec import Event
# The refusal has no inventory rows. Real resource-backed full records are
# separately checked by authenticated artifact TLS, never simulated here.
def forbidden_record(*args):raise AssertionError('Refusal attempted inventory serialization')
with patch.dict(sys.modules,{'els_server.domain.fashion_state':SimpleNamespace(record=forbidden_record,empty_record=forbidden_record)}):
    from els_server.protocol.equipment_spell_exchange import request
    from els_server.domain import equipment_spell_exchange_flow as flow

def actor():
    account=SimpleNamespace(uid=1,account_id=8,characters=object(),store=SimpleNamespace(uid=1))
    root=SimpleNamespace(character_accounts={1:account});account.root=root
    session=SimpleNamespace(item_test=True,client_build='dx11_260923',role='game',phase='town_ready',account=account,identity={'id':8},released=False)
    session.application=SimpleNamespace(accounts={8:root},playing={8:session})
    return session

class ColoredTransferAdmission(unittest.TestCase):
    def event(self, group=11):
        return Event(0x202, kind=0x971, payload=struct.pack('>QQii',1,2,group,-1))

    def assert_refusal(self, reply):
        self.assertEqual(len(reply),1)
        self.assertEqual((reply[0].event_id,reply[0].kind),(0x201,0x972))
        self.assertEqual(reply[0].payload,struct.pack('>iI',2005,0))

    def test_original_columns_only(self):
        for group in (9,10,11):
            self.assertEqual(request(self.event(group).payload),(1,2,group,-1))
        for group,index in ((12,0),(11,0),(9,8)):
            with self.assertRaises(ValueError):request(struct.pack('>QQii',1,2,group,index))

    def test_replaced_playing_lease_refuses_before_account_access(self):
        session=actor();session.application.playing[8]=object()
        self.assert_refusal(flow.handle(session,self.event(),1))

    def test_selected_store_must_match_owned_character(self):
        session=actor();session.account.store.uid=2
        self.assert_refusal(flow.handle(session,self.event(9),1))

if __name__=='__main__':unittest.main()
