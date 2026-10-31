"""Extra source replacement, retention and original-producer goldens."""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import hashlib,importlib.util,json,sys,unittest
from tests.test_native_skill_delivery_sources import copy_event

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'references/native-server-attributes-20261027-v1'


class ExtraSkillInputsTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        import els_server.domain as domain
        self.stack.enter_context(patch.object(domain,'__path__',[str(A/'els_server/domain'),*domain.__path__]))
        self.stack.enter_context(patch.dict(sys.modules))
        for name in('native_skill_delivery_sources','native_extra_skill_inputs'):
            spec=importlib.util.spec_from_file_location('els_server.domain.'+name,A/'els_server/domain'/(name+'.py'))
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            self.stack.enter_context(patch.object(domain,name,module,create=True))
        self.port=module

    def test_whole_original_copy_and_increment_goldens_keep_distinct_grades(self):
        golden=json.loads((A/'native-extra-skill-copy-source-goldens-v2.json').read_bytes())
        raw=Path(self.port.__file__).read_bytes()
        # The accepted copy/insert functions retain their exact bytes. The
        # only later addition is the separately qualified extraction function.
        self.assertEqual(raw.count(b'\n\ndef after_extraction'),1)
        inverse=raw.split(b'\n\ndef after_extraction',1)[0]
        self.assertEqual(golden['source_sha256'],hashlib.sha256(inverse).hexdigest())
        self.assertEqual((golden['copied_controls'],golden['insert_controls']),(2,5))
        gate=json.loads((A/'native-extra-skill-copy-gate-goldens.json').read_bytes())
        self.assertEqual(gate['cases'],6)
        self.assertEqual(gate['source_sha256'],golden['source_sha256'])
        for row in gate['rows']:
            source=next(r for r in golden['rows']if r['label']==row['writer_source'])
            self.assertEqual(row['native'],source['extra'])
        for row in golden['rows']:
            copied=self.port.CopiedRanks(tuple(map(tuple,row['ordinary'])),(),tuple(map(tuple,row['extra'])))
            self.assertEqual(self.port.after_copy(copied),tuple(map(tuple,row['native'])))
        previous=tuple(map(tuple,golden['rows'][-1]['native']))
        for row in golden['inserts']:
            previous=self.port.after_increment(previous,(tuple(row['input']),))
            self.assertEqual(previous,tuple(map(tuple,row['native'])))

    def test_original_extraction_removes_only_the_exact_owned_grade(self):
        golden=json.loads((A/'native-extra-skill-extraction-phase-goldens.json').read_bytes())
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(self.port.__file__).read_bytes()).hexdigest())
        self.assertEqual(golden['cases'],6)
        previous=tuple(map(tuple,golden['initial']))
        for row in golden['rows']:
            previous=self.port.after_extraction(previous,tuple(row['pair']))
            self.assertEqual(previous,tuple(map(tuple,row['native'])))
        self.assertIsNone(self.port.after_extraction(None,(100,1)))

    def test_extra_copy_is_independent_of_skipped_ordinary_branch(self):
        _,fields=copy_event()
        parsed=self.port.from_character_field(dict(fields)['0x14e'])
        self.assertEqual(parsed.ordinary,((25410,4),));self.assertEqual(parsed.extra,((25410,4),))
        self.assertIsNone(self.port.after_increment(None,((100,1),)))
        self.assertEqual(self.port.after_copy(parsed),parsed.extra)
        empty=self.port.CopiedRanks((),(),())
        self.assertEqual(self.port.after_copy(empty),())

    def test_shape_and_pair_bounds_reject_without_guessing_empty_sources(self):
        _,fields=copy_event();raw=dict(fields)['0x14e']
        for bad in(raw[:-1],raw+b'\0',raw[-16:],list(raw)):
            with self.assertRaises(ValueError):self.port.from_character_field(bad)
        parsed=self.port.CopiedRanks((),(),())
        with self.assertRaises(ValueError):self.port.after_copy(None)
        for bad in(((100,0),),((True,1),),((100,True),),((2**31,1),),((100,256),),[[100,1]]):
            with self.assertRaises(ValueError):self.port.after_increment((),bad)


if __name__=='__main__':unittest.main()
