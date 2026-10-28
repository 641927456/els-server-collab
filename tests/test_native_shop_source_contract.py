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

    def test_frozen_random_password_fixture_does_not_allow_edited_source(self):
        name='launchers/friends-v41/Program.cs';raw=(checker.ROOT/name).read_bytes()
        self.assertEqual(guard.violations(name,raw),[])
        changed=raw.replace(b'Fixture-Only-',b'Changed-Fixture-',1)
        self.assertNotEqual(changed,raw)
        self.assertTrue(guard.violations(name,changed))


if __name__=='__main__':unittest.main()
