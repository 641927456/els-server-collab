"""Original788 source order and conservative canonical snapshot boundaries."""
import importlib.util,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'references/native-server-attributes-20261027-v1'
SPEC=importlib.util.spec_from_file_location('candidate_set_registration_inputs',A/'els_server/domain/native_set_registration_inputs.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def source(rows,revision=1,owner=1001):
    return dict(owner=owner,character=dict(uid=1001,avatar_set_source=dict(revision=revision,rows=rows)))


class NativeRegistrationInputTests(unittest.TestCase):
    def test_all_current_native_source_orders_and_explicit_context_match(self):
        proof=json.loads((A/'native-avatar-registration-source-goldens.json').read_bytes())
        self.assertTrue(proof['ok']);self.assertEqual(len(proof['rows']),6)
        for row in proof['rows']:
            value=M.build(source(tuple(tuple(v)for v in row['input'])))
            self.assertEqual(value['registrations'],tuple(tuple(v)for v in row['native']))
            self.assertEqual(value['preset'],row['current_preset'])
            self.assertTrue(value['preset_is_relevant'])
            self.assertEqual(value['restoration'].kind,0x788)

    def test_absent_registration_keeps_the_preset_operand_irrelevant(self):
        value=M.build(source((),revision=0))
        self.assertEqual(value['registrations'],())
        self.assertFalse(value['preset_is_relevant'])
        self.assertIsNone(value['restoration'])

    def test_incomplete_foreign_or_unqualified_context_never_defaults_to_empty(self):
        rows=tuple((0,0,i,100+i)for i in range(6))
        for invalid in(source(rows,revision=0),source(rows,revision=True),source(rows,owner=1002),
                       source(rows[:-1]),source(tuple(list(v)for v in rows)),
                       source(tuple((1,*v[1:])for v in rows)),
                       source(tuple((0,0,i,100)for i in range(6)))):
            with self.assertRaises(ValueError):M.build(invalid)


if __name__=='__main__':unittest.main()
