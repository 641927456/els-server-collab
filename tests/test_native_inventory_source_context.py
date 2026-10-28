"""Copied owner/status evidence and branch-irrelevance admission boundary."""
from contextlib import ExitStack
import importlib.util,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'references/native-server-attributes-20261027-v1'


class InventorySourceContextTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        import els_server.domain as domain
        self.stack.enter_context(patch.object(domain,'__path__',[str(A/'els_server/domain'),*domain.__path__]))
        self.fields={'0x306':bytes(1)}
        self.stack.enter_context(patch.dict(sys.modules,{
            'els_server.domain.native_current_character_inputs':SimpleNamespace(build=lambda *a,**kw:dict(owner_uid=1001)),
            'els_server.protocol.local_messages':SimpleNamespace(character_unit_fields=lambda **kw:tuple(self.fields.items()))}))
        spec=importlib.util.spec_from_file_location('candidate_inventory_context',A/'els_server/domain/native_inventory_source_context.py')
        self.port=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.port)

    def test_original_full_copy_controls_bind_current_owner_and_copied_status(self):
        proof=json.loads((A/'native-inventory-owner-source-goldens.json').read_bytes())
        self.assertTrue(proof['ok']);self.assertEqual(len(proof['rows']),3)
        for row in proof['rows']:
            self.fields['0x306']=bytes([row['emitted306']])
            source=dict(items=tuple(dict(template=v['template'])for v in row['items']),character={},ordinary_slots=())
            actual=self.port.build(source,previous_rank=0)
            self.assertEqual(actual['owner_status'],(row['inventory_owner_is_current_Unit'],bool(row['Unit7BD'])))
            self.assertFalse(actual['special_mode_operand_is_relevant'])

    def test_unknown_status_and_relevant_special_authority_never_receive_guessed_defaults(self):
        source=dict(items=(),character={},ordinary_slots=())
        for raw in(b'',b'\2',b'\0\0'):
            self.fields['0x306']=raw
            with self.assertRaises(ValueError):self.port.build(source,previous_rank=0)
        self.fields['0x306']=b'\0'
        source['items']=(dict(template=next(iter(self.port.SPECIAL_IDS))),)
        with self.assertRaisesRegex(ValueError,'user30'):
            self.port.build(source,previous_rank=0)


if __name__=='__main__':unittest.main()
