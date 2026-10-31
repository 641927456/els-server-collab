"""Execute exact archived pure definitions without importing private resources."""
from pathlib import Path
import ast,struct,unittest

ARCHIVE=Path(__file__).resolve().parents[1]

class EntryFailurePayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ARCHIVE/'source/common/els_server/domain/town_travel.py'
        tree=ast.parse(path.read_bytes())
        names={'DestinationRequirementError','entry_failure_code','entry_failure_payload'}
        nodes=[node for node in tree.body if isinstance(node,(ast.ClassDef,ast.FunctionDef))and node.name in names]
        assert {node.name for node in nodes}==names
        env={'struct':struct,'__name__':'archived_entry_failure_payload'}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
        cls.error_type=env['DestinationRequirementError'];cls.encode=staticmethod(env['entry_failure_payload'])

    def test_generic_scene_failure_has_zero_detail_fields(self):
        for error in (None,ValueError('scene'),OverflowError('encoding')):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(self.encode(error),struct.pack('>5i',515,0,0,0,0))

    def test_actual_minimum_level_occupies_second_native_field(self):
        for minimum in (10,15,70,99):
            with self.subTest(minimum=minimum):
                self.assertEqual(self.encode(self.error_type('level',level=minimum)),struct.pack('>5i',518,minimum,0,0,0))

    def test_required_dungeon_occupies_third_native_field(self):
        self.assertEqual(self.encode(self.error_type('clear',dungeon=30092)),struct.pack('>5i',519,0,30092,0,0))

    def test_required_quest_occupies_fourth_native_field(self):
        self.assertEqual(self.encode(self.error_type('quest',quest=26640)),struct.pack('>5i',1620,0,0,26640,0))

if __name__=='__main__':unittest.main()
