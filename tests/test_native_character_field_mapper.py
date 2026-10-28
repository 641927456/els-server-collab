"""Source contracts without the untracked runtime catalog.

Full1170 real-resource wire comparisons remain separate frozen evidence.
CI verifies the exact inverse refactor and generation/field boundaries.
"""
import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'references/native-server-attributes-20261027-v1'

def load(name,relative):
    spec=importlib.util.spec_from_file_location(name,REFERENCE/relative)
    result=importlib.util.module_from_spec(spec)
    sys.modules[name]=result
    spec.loader.exec_module(result)
    return result

class CurrentCharacterFieldTests(unittest.TestCase):
    def test_shared_mapper_is_an_exact_inverse_of_the_actual_accepted_parent(self):
        golden=json.loads((REFERENCE/'native-current-character-field-goldens.json').read_bytes())
        self.assertEqual(golden['cases'],1170)
        self.assertEqual(len(golden['rows']),1170)
        self.assertEqual(len({row['class_id']for row in golden['rows']}),195)
        for channel in('online','local'):
            profile=json.loads((ROOT/'channels/pr597-remaining-accepted-20261027-v2.json').read_bytes())
            parent=next(row for row in profile['channels'][channel]['files']if row['path']=='els_server/protocol/local_messages.py')
            original=ROOT/parent['source']
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),golden['parent_sha256'])
            source=REFERENCE/'els_server/protocol/local_messages.py'
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),golden['source_sha256']['writer'])
            tree=ast.parse(source.read_bytes());nodes=[]
            for node in tree.body:
                if isinstance(node,ast.FunctionDef)and node.name=='character_unit':continue
                if isinstance(node,ast.FunctionDef)and node.name=='character_unit_fields':
                    node.name='character_unit'
                    loop=next(v for v in node.body if isinstance(v,ast.For))
                    append=next(v for v in loop.body if isinstance(v,ast.Expr)
                        and isinstance(v.value,ast.Call)and isinstance(v.value.func,ast.Attribute)
                        and v.value.func.attr=='append')
                    self.assertIsInstance(append.value.args[0],ast.Tuple)
                    append.value.args=[append.value.args[0].elts[1]]
                    node.body[-1]=ast.parse("return b''.join(fields)").body[0]
                nodes.append(node)
            tree.body=nodes
            self.assertEqual(ast.dump(tree,include_attributes=False),ast.dump(ast.parse(original.read_bytes()),include_attributes=False))

    def test_source_identity_and_actual_emitted_field_mismatches_are_rejected(self):
        import els_server.domain as domain
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in('native_power_kernel','native_rank_coefficient','native_character_context','native_resonance_source_groups'):
                loaded=load('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,loaded,create=True))
            context=load('candidate_current_character_inputs','els_server/domain/native_current_character_inputs.py')
            golden=json.loads((REFERENCE/'native-current-character-field-goldens.json').read_bytes())
            self.assertEqual(hashlib.sha256(Path(context.__file__).read_bytes()).hexdigest(),golden['source_sha256']['inputs'])
            base=struct.pack('>7f',10000.,320.,320.,0.,0.,80.,80.)
            fields={'0x3fc':bytes(4),'0xb6':base,'0xd2':base,'0x6a':bytes(4),
                '0x3c5':bytes(25),'0x307':bytes(4),'0x471':struct.pack('>iQiB',0,0,0,0)}
            writer=SimpleNamespace(character_unit_fields=lambda **kw:tuple(fields.items()))
            stack.enter_context(patch.dict(sys.modules,{'els_server.protocol.local_messages':writer}))
            snapshot=dict(owner=1,account_id=2,character=dict(uid=1,title=0),items=(),ordinary_slots=(),
                resonance=dict(account=dict(enabled=False,level=0,experience=0),profile=None),companions={},world_effects={})
            snapshot['source_sha256']=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True,
                separators=(',',':'),allow_nan=False).encode('utf8')).hexdigest()
            value=context.build(snapshot,previous_rank=0)
            self.assertEqual((value['owner_uid'],value['full_copy'].rank,value['resonance_level']),(1,0,0))
            for key,bad in(('0x3fc',b'\0\0\0\1'),('0xd2',bytes(28)),('0x6a',b'\1'*4),('0x3c5',bytes(24)),
                            ('0x307',struct.pack('>i',1)),('0x471',struct.pack('>iQiB',1,0,0,0))):
                old=fields[key];fields[key]=bad
                try:
                    with self.assertRaises(ValueError):context.build(snapshot,previous_rank=0)
                finally:fields[key]=old
            snapshot['character']['title']=1
            with self.assertRaisesRegex(ValueError,'changed after capture'):
                context.build(snapshot,previous_rank=0)

if __name__=='__main__':unittest.main()
