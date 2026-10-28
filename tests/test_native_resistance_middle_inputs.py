"""Independent original pet/Artifact middle goldens and separate title gates."""
from contextlib import ExitStack
import importlib.util,json,struct,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'references/native-server-attributes-20261027-v1'


class ResistanceMiddleInputTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        import els_server.domain as domain
        self.stack.enter_context(patch.object(domain,'__path__',[str(A/'els_server/domain'),*domain.__path__]))
        self.stack.enter_context(patch.dict(sys.modules))
        for name in('native_rank_coefficient','native_pve_rank_coefficient','native_resistance_middle_inputs'):
            spec=importlib.util.spec_from_file_location('els_server.domain.'+name,A/'els_server/domain'/(name+'.py'))
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            if hasattr(module,'PROJECT_ROOT'):module.PROJECT_ROOT=ROOT
            self.stack.enter_context(patch.object(domain,name,module,create=True))
        self.port=module

    def test_original_eight_pet_and_180_artifact_phases_keep_exact_order_and_values(self):
        for family,count in(('pet',8),('artifact',180)):
            proof=json.loads((A/f'native-resistance-{family}-middle-goldens.json').read_bytes())
            self.assertTrue(proof['ok']);self.assertEqual(len(proof['rows']),count)
            definitions={int(k):v for k,v in proof['definitions'].items()}
            for row in proof['rows']:
                source=self.port.MiddleSources((),tuple(row['options'])if family=='pet'else(),tuple(row['options'])if family=='artifact'else())
                actual=self.port.merge(tuple(row['before']),definitions,source,mode=0,rank=0,
                    pve_context=dict(stage=0,grade=0,first_count=0,second_count=0))
                self.assertEqual(struct.pack('<6f',*actual['values']),struct.pack('<6f',*row['native']))
                self.assertEqual(tuple(v for v,w in actual['callbacks']),tuple(v for v in row['options']if v in definitions))

    def test_title_filter_pet_exclusion_and_ungated_artifact_remain_distinct(self):
        definitions={1:dict(RESIST_ENCHANT=dict(BLAZE=350),PVP_ONLY=1),
                     2:dict(RESIST_ENCHANT=dict(BLAZE=150),PVP_ONLY=1)}
        source=self.port.MiddleSources((1,),(2,),(2,))
        for mode,expected,callbacks in((0,300.,(2,2)),(1,500.,(1,2))):
            result=self.port.merge((0.,)*6,definitions,source,mode=mode,rank=0,
                pve_context=dict(stage=0,grade=0,first_count=0,second_count=0))
            self.assertEqual(result['values'],(expected,0.,0.,0.,0.,0.))
            self.assertEqual(tuple(v for v,w in result['callbacks']),callbacks)

    def test_nonempty_pet_requires_runtime_presence_and_collection_is_separate(self):
        source=dict(option_sources=(('title',(1,)),('pet',(2,)),('artifact',(3,)),('collection',(4,))))
        with self.assertRaisesRegex(ValueError,'runtime presence'):
            self.port.from_auxiliary(source,mode=0,pet_runtime_ready=False)
        self.assertEqual(self.port.from_auxiliary(source,mode=0,pet_runtime_ready=True),self.port.MiddleSources((1,),(2,),(3,)))
        # The original mode1 branch excludes pets; it need not invent an
        # available runtime object for that irrelevant source operand.
        self.port.from_auxiliary(source,mode=1,pet_runtime_ready=False)
        with self.assertRaises(ValueError):self.port.from_auxiliary(source,mode=0,pet_runtime_ready=1)
        for malformed in(self.port.MiddleSources((),(True,),()),self.port.MiddleSources((),(),[])):
            with self.assertRaises(ValueError):
                self.port.merge((0.,)*6,{},malformed,mode=0,rank=0,pve_context={})


if __name__=='__main__':unittest.main()
