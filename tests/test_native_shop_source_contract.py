"""Changed signed bytes and edited credential fixtures must fail before publication."""
import base64,copy,json,unittest
from tools import repository_guard as guard
from tools import verify_native_shop_flow_20261029 as checker


class NativeShopSourceTests(unittest.TestCase):
    def test_complete_source_contract(self):checker.verify()

    def test_changed_signed_payload_rejected(self):
        doc=checker.read(checker.L/'runtime-files.signed.json')
        xml=checker.public_xml((checker.L/'AutoUpdate.cs').read_text(encoding='utf-8'))
        raw=bytearray(base64.b64decode(doc['payload']));raw[len(raw)//2]^=1
        doc['payload']=base64.b64encode(raw).decode()
        with self.assertRaises(AssertionError):checker.envelope(doc,xml)

    def test_receipt_refuses_wrong_LOCAL_pointer_or_unverified_GUI_claim(self):
        receipt=checker.read(checker.F/'accepted-delivery.json')
        source=checker.read(checker.L/'source-manifest.json')
        current=checker.read(checker.ROOT/'channels/current-engine.json')
        profile=checker.read(checker.ROOT/'channels/native-force-guild-flow-accepted-20261029-v1.json')
        wrong=copy.deepcopy(current)
        wrong['accepted']['local']['formal_manifest_sha256']=source['actual_current_parents']['local']['manifest_sha256']
        with self.assertRaises(AssertionError):checker.accepted_delivery(receipt,source,wrong,profile)
        changed=copy.deepcopy(receipt);changed['natural_GUI']=True
        with self.assertRaises(AssertionError):checker.accepted_delivery(changed,source,current,profile)

    def test_frozen_random_password_fixture_does_not_allow_edited_source(self):
        name='launchers/friends-v41/Program.cs';raw=(checker.ROOT/name).read_bytes()
        self.assertEqual(guard.violations(name,raw),[])
        changed=raw.replace(b'Fixture-Only-',b'Changed-Fixture-',1)
        self.assertNotEqual(changed,raw)
        self.assertTrue(guard.violations(name,changed))


if __name__=='__main__':unittest.main()
