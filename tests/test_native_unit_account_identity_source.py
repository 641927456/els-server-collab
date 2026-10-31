"""Reject an extra payload change even when account edits still invert."""
import ast,copy,unittest
from tools import verify_native_unit_account_identity_20261029 as check

class UnitIdentitySourceTests(unittest.TestCase):
    def test_five_source_parent_contract(self):check.verify()

    def test_unrelated_source_append_cannot_restore_parent(self):
        delta=check.read(check.F/'delta.json');rules=check.read(check.F/'source-inverse.json')
        path='els_server/protocol/local_messages.py';row=delta['channels']['online'][path]
        original=(check.ROOT/row['before_source']).read_bytes()
        altered=(check.ROOT/row['source']).read_bytes()+b'\n_UNRELATED_PROTOCOL_OVERRIDE=True\n'
        self.assertNotEqual(check.restored(altered,path,rules),original)
        self.assertNotEqual(ast.dump(ast.parse(check.restored(altered,path,rules))),ast.dump(ast.parse(original)))

    def test_removing_a_new_owner_guard_fails_the_exact_inverse(self):
        d=check.read(check.F/'delta.json');rules=check.read(check.F/'source-inverse.json')
        path='els_server/protocol/local_messages.py';raw=(check.ROOT/d['channels']['online'][path]['source']).read_bytes()
        altered=raw.replace(b"type(account_id)is not int",b"False",1)
        self.assertNotEqual(altered,raw)
        with self.assertRaises(AssertionError):check.restored(altered,path,rules)

if __name__=='__main__':unittest.main()
