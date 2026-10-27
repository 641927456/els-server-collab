"""Portable original-native goldens; actual gameplay acceptance is separate."""
from dataclasses import replace
from contextlib import closing
from pathlib import Path
import importlib.util
import json
import math
import sqlite3
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT/'references/native-server-attributes-20261027-v1'


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, REFERENCE/relative)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


class NativeServerAttributeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.passives = module('candidate_native_passives', 'els_server/domain/native_passive_attributes.py')
        cls.equipment = module('candidate_native_equipment', 'els_server/domain/native_equipment_attributes.py')
        cls.projection = module('candidate_native_projection', 'els_server/domain/native_attribute_projection.py')
        cls.loader = module('candidate_native_rule_loader', 'els_server/domain/native_attribute_rules.py')
        cls.wire = module('candidate_native_attribute_wire', 'els_server/protocol/native_attribute_messages.py')
        cls.power = module('candidate_native_power_kernel', 'els_server/domain/native_power_kernel.py')
        cls.snapshot = module('candidate_native_attribute_snapshot', 'els_server/storage/native_attribute_snapshot.py')
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':cls.power}):
            cls.conditions = module('candidate_native_conditions', 'els_server/domain/native_conditional_power_attributes.py')
            cls.option_data = module('candidate_native_option_data', 'els_server/domain/native_option_data_merge.py')
            cls.cooldown_map = module('candidate_native_cooldown_map', 'els_server/domain/native_cooldown_map.py')
            cls.slopes = module('candidate_native_slopes', 'els_server/domain/native_power_slopes.py')
            with patch.dict(sys.modules,{'els_server.domain.native_power_slopes':cls.slopes}):
                cls.contexts = module('candidate_native_contexts', 'els_server/domain/native_condition_contexts.py')
            cls.option_power_maps = module('candidate_native_option_maps', 'els_server/domain/native_option_power_maps.py')
            cls.option_metadata = module('candidate_native_option_metadata', 'els_server/domain/native_option_metadata.py')
            cls.option_conditions = module('candidate_native_option_conditions', 'els_server/domain/native_option_condition_inputs.py')
            cls.extension = module('candidate_native_extension_inputs', 'els_server/domain/native_extension_inputs.py')
            with patch.dict(sys.modules,{'els_server.domain.native_extension_inputs':cls.extension}):
                cls.resonance = module('candidate_native_resonance', 'els_server/domain/native_resonance_attributes.py')
            cls.option_scalars = module('candidate_native_option_scalars', 'els_server/domain/native_option_scalar_inputs.py')
            with patch.dict(sys.modules,{'els_server.domain.native_option_scalar_inputs':cls.option_scalars}):
                cls.option_merge = module('candidate_native_option_merge', 'els_server/domain/native_option_scalar_merge.py')
            with patch.dict(sys.modules,{'els_server.domain.native_option_data_merge':cls.option_data,
                'els_server.domain.native_option_scalar_merge':cls.option_merge}):
                cls.option_record = module('candidate_native_option_record', 'els_server/domain/native_option_record_merge.py')
        cls.power_goldens = json.loads((REFERENCE/'native-power-goldens.json').read_bytes())
        cls.goldens = json.loads((REFERENCE/'native-phase-goldens.json').read_bytes())
        cls.rules = json.loads((REFERENCE/'passive-stat-rules.json').read_bytes())['rules']
        cls.definitions = {int(k):v for k,v in cls.goldens['definitions'].items()}

    def test_rule_source_is_pinned_and_deeply_immutable(self):
        raw=(REFERENCE/'passive-stat-rules.json').read_bytes()
        loaded=self.loader.decode(raw)
        self.assertEqual(len(loaded),72)
        with self.assertRaises(TypeError):
            loaded[0]['skill']=0
        with self.assertRaises(TypeError):
            loaded[0]['operations'][0]['target']=0
        with self.assertRaises(ValueError):
            self.loader.decode(raw+b' ')

    def test_current_original_native_scalar_goldens(self):
        basis = tuple(self.goldens['basis'])
        for case in self.goldens['cases']:
            ranks = {int(k):v for k,v in case['query_ranks'].items()}
            with self.subTest(phase=case['phase'], ranks=ranks, pvp=case['pvp']):
                if case['phase']=='naked':
                    actual = self.passives.apply_naked(basis,ranks,self.definitions,
                        pvp=case['pvp'],extension5=0.,extension16=0.)
                else:
                    actual = self.passives.apply(basis,ranks,self.definitions,
                        {sid:(sid,rank)for sid,rank in ranks.items()},self.rules,
                        phase_pvp=case['pvp'],unit_pvp=False,flat_attack=0.,flat_defense=0.)
                self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*case['native']))

    def test_refinement_adds_only_to_positive_native_fields(self):
        actual = self.equipment.merge_refinement((-1.,0.,100.,4.,5.,0.,-1.),
            (1.,2.,3.,4.,5.,6.,7.),scale=None)
        self.assertEqual(actual,(-1.,0.,103.,4.,5.,0.,-1.))

    def test_refinement_scale_rounds_before_native_addition(self):
        # Golden from original scalar instructions, not the template multiplier.
        actual = self.equipment.merge_refinement((1.,2.,3.,4.,5.,6.,7.),
            (1.,2.,3.,4.,5.,6.,7.),scale=.5)
        self.assertEqual(actual,(1.5,3.,4.5,4.,5.,9.,10.5))

    def test_sourced_refinement_mode_requires_original_registration(self):
        source='cd622db6fe266e6a28323c1eb0e16a565def39f7008c1e21858684b7548f4738'
        from types import SimpleNamespace
        with patch.dict(sys.modules,{'els_server.domain.equipment_reforge_rules':
            SimpleNamespace(catalog=lambda:dict(source_resource_sha256=source))}):
            self.assertIsNone(self.equipment.refinement_scale_for_mode(0))
            self.assertEqual(struct.pack('<f',self.equipment.refinement_scale_for_mode(1)),bytes.fromhex('cdcccc3e'))
        with patch.dict(sys.modules,{'els_server.domain.equipment_reforge_rules':
            SimpleNamespace(catalog=lambda:dict(source_resource_sha256='unknown'))}):
            with self.assertRaises(ValueError):self.equipment.refinement_scale_for_mode(1)

    def power_arguments(self, case):
        return dict(stat_fields={int(k,16):v for k,v in case['stat_fields'].items()},
            data_fields={int(k,16):v for k,v in case['data_fields'].items()},
            maps={int(k,16):{tuple(key)if isinstance(key,list)else key:
                value for key,value in rows}
                for k,rows in case['maps'].items()},stat610=case['stat610'],
            class_kind=case['class_kind'],max_mp=case['max_mp'],unit_factor=case['unit_factor'])

    def test_full_native_power_kernel_dense_original_goldens(self):
        # Six independently executed synthetic compositions exercise all42
        # scalar inputs, five data inputs and six original map groups.
        self.assertEqual(len(self.power_goldens['cases']),8)
        # The last two cases retain opposite flag values at the same threshold.
        for row in self.power_goldens['cases'][-2:]:
            probabilities=[key[0]for key,value in row['maps']['0x3f8']]
            self.assertLess(len(set(probabilities)),len(probabilities))
        for index,case in enumerate(self.power_goldens['cases']):
            with self.subTest(index=index):
                actual=self.power.calculate(**self.power_arguments(case))
                self.assertEqual(struct.pack('<2f',*actual),struct.pack('<2f',*case['native']))

    def test_power_kernel_rejects_missing_maps_and_singular_values(self):
        for label in('missing_map','singular','client_total'):
            args=self.power_arguments(self.power_goldens['cases'][0])
            if label=='missing_map':args['maps'].pop(0x788)
            elif label=='singular':args['stat_fields'][0x7e0]=1.
            else:args['stat_fields'][0x3048]=12345.
            with self.subTest(label=label),self.assertRaises(ValueError):self.power.calculate(**args)

    def test_option_scalars_match_independent_original_catalog_records(self):
        goldens=json.loads((REFERENCE/'native-option-scalar-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),136)
        self.assertEqual(len(self.option_scalars.FIELDS),57)
        for index,row in enumerate(goldens['cases']):
            with self.subTest(index=index):
                actual=self.option_scalars.scalar_inputs(row['definition'])
                expected={int(key,16):value for key,value in row['native'].items()}
                self.assertEqual(set(actual),set(expected))
                for offset in actual:
                    self.assertEqual(struct.pack('<f',actual[offset]),struct.pack('<f',expected[offset]))

    def test_option_scalar_source_rejects_nonfinite_and_container_inputs(self):
        for value in (float('nan'),float('inf'),{},True,'0.1'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.option_scalars.scalar_inputs({'m_fPercentCritical':value})
        self.assertEqual(self.option_scalars.scalar_inputs({})[0xf4],0.)
        # The original i-prefixed animation field still accepts fractions.
        self.assertEqual(self.option_scalars.scalar_inputs({'m_iAnimationSpeedRate':.125})[0x18],.125)

    def test_native_option_mp_overlap_adds_before_percentage_conversion(self):
        goldens=json.loads((REFERENCE/'native-option-scalar-goldens.json').read_bytes())
        for row in goldens['mp_overlap_cases']:
            actual=self.option_scalars.scalar_inputs(row['definition'])
            for key,value in row['native'].items():
                self.assertEqual(struct.pack('<f',actual[int(key,16)]),struct.pack('<f',value))

    def test_native_option_scalar_merge_condition_modes_and_source_line(self):
        goldens=json.loads((REFERENCE/'native-option-scalar-merge-goldens.json').read_bytes())
        before={int(key,16):value for key,value in goldens['base'].items()}
        source={int(key,16):value for key,value in goldens['source'].items()}
        self.assertEqual(len(goldens['cases']),120)
        for index,row in enumerate(goldens['cases']):
            with self.subTest(index=index):
                actual=self.option_merge.merge_scalar_phase(before,source,**row['args'])
                for key,value in row['native'].items():
                    self.assertEqual(struct.pack('<f',actual[int(key,16)]),struct.pack('<f',value))

    def test_original_option_data_merge_hp_flat_and_conditional_attacks(self):
        goldens=json.loads((REFERENCE/'native-option-data-merge-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),135)
        for index,row in enumerate(goldens['cases']):
            with self.subTest(index=index):
                actual=self.option_data.merge_attribute_data(tuple(goldens['before']),tuple(goldens['source']),**row['args'])
                self.assertEqual(struct.pack('<13f',*actual),struct.pack('<13f',*row['native']))

    def test_original_cooldown_map_addition_preserves_zero_and_existing_keys(self):
        goldens=json.loads((REFERENCE/'native-cooldown-category-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),243)
        for index,row in enumerate(goldens['cases']):
            with self.subTest(index=index):
                actual=self.cooldown_map.apply_cooldown_categories(
                    {int(k,16):v for k,v in row['scalars'].items()},
                    {int(k):v for k,v in row['before'].items()})
                expected={int(k):v for k,v in row['native'].items()}
                self.assertEqual(set(actual),set(expected))
                for key in expected:
                    self.assertEqual(struct.pack('<f',actual[key]),struct.pack('<f',expected[key]))

    def test_original_option_record_wrapper_retains_phase_order(self):
        goldens=json.loads((REFERENCE/'native-option-record-merge-goldens.json').read_bytes())
        before={int(k,16):v for k,v in goldens['base'].items()}
        source={int(k,16):v for k,v in goldens['source'].items()}
        for index,row in enumerate(goldens['cases']):
            with self.subTest(index=index):
                actual,data=self.option_record.merge_option_record(before,source,
                    tuple(goldens['before_data']),tuple(goldens['source_data']),**row['args'])
                for key,value in row['native'].items():
                    self.assertEqual(struct.pack('<f',actual[int(key,16)]),struct.pack('<f',value))
                self.assertEqual(struct.pack('<13f',*data),struct.pack('<13f',*row['native_data']))

    def test_original_option_stat_uses_base_hp_and_five_fields(self):
        goldens=json.loads((REFERENCE/'native-option-direct-stat-goldens.json').read_bytes())
        for row in goldens['cases']:
            definition={k:v for k,v in row['STAT'].items()if k in self.option_data.STAT_KEYS}
            actual=self.option_data.direct_option_stats(definition)
            self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*row['native']))
        with self.assertRaises(ValueError):
            self.option_data.direct_option_stats({'m_fMaxHP':157000.})

    def test_original_option_power_map_sources_and_merge(self):
        goldens=json.loads((REFERENCE/'native-option-power-maps-goldens.json').read_bytes())
        decode=lambda rows:{tuple(k)if type(k)is list else k:v for k,v in rows}
        self.assertEqual(len(goldens['sources']),21)
        self.assertEqual(len(goldens['cases']),84)
        sources=[]
        for row in goldens['sources']:
            source=self.option_power_maps.source_map_inputs(row['definition'])
            self.assertEqual(source,dict(capability=tuple(row['capability']),
                probability=decode(row['probability']),additional=tuple(row['additional'])))
            sources.append(source)
        for index,row in enumerate(goldens['cases']):
            with self.subTest(index=index):
                before=row['before']
                actual=self.option_power_maps.merge_map_inputs(decode(before['capability']),
                    decode(before['probability']),tuple(before['additional']),
                    sources[row['source']],**row['args'])
                expected=row['native']
                self.assertEqual(actual,(decode(expected['capability']),
                    decode(expected['probability']),tuple(expected['additional'])))

    def test_current_resonance_definition_matches_whole_original_registration(self):
        raw=(ROOT/'els_server/data/resonance2026-stats.json').read_bytes()
        goldens=json.loads((REFERENCE/'native-resonance-resource-goldens.json').read_bytes())
        definitions=self.resonance.definition_inputs(raw)
        self.assertEqual(set(definitions),{int(k)for k in goldens['rows']})
        for key,row in goldens['rows'].items():
            value=definitions[int(key)]
            self.assertEqual(struct.pack('<f',value[0]),struct.pack('<f',row[0]))
            self.assertEqual(value[1:],tuple(row[1:]))
        with self.assertRaises(ValueError):self.resonance.definition_inputs(raw+b' ')

    def test_whole_native_resonance_phase_current_dense_and_absent_managers(self):
        goldens=json.loads((REFERENCE/'native-resonance-phase-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),36)
        before={int(k,16):v for k,v in goldens['before'].items()}
        for index,row in enumerate(goldens['cases']):
            with self.subTest(index=index):
                definitions=goldens['definitions'][row['profile']]
                if definitions is not None:definitions={int(k):tuple(v)for k,v in definitions.items()}
                actual=self.resonance.apply_resonance(before,
                    {int(k):v for k,v in row['points'].items()},tuple(row['override']),
                    definitions,**row['args'])
                expected=({int(k,16):v for k,v in row['native_fields'].items()},
                    {int(k):v for k,v in row['native_damage'].items()},
                    {int(k):v for k,v in row['native_cooldown'].items()})
                self.assertEqual(actual,expected)

    def test_condition_contexts_match_original_source_phase(self):
        goldens=json.loads((REFERENCE/'native-condition-context-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),20)
        for index,row in enumerate(goldens['cases']):
            args=dict(row['args']);args['cooldown_categories']={int(k):v for k,v in args['cooldown_categories'].items()}
            with self.subTest(index=index):
                actual=self.contexts.build_condition_contexts(tuple(row['resistances']),**args)
                self.assertEqual(actual,{int(k,16):v for k,v in row['native'].items()})

    def test_intermediate_conditions_keep_data_and_extended_scalar_destinations_separate(self):
        goldens=json.loads((REFERENCE/'native-conditional-power-goldens.json').read_bytes())
        for index,row in enumerate(goldens['cases']):
            values={int(k,16):v for k,v in row['fields'].items()}
            data={k:values[k]if k in values else .137 for k in self.conditions.INTERMEDIATE_DATA}
            scalars={k:values[k]for k in self.conditions.INTERMEDIATE_SCALARS}
            with self.subTest(index=index):
                actual_data,actual_scalars=self.conditions.apply_intermediate(data,scalars,
                    tuple(tuple(v)for v in row['conditions']),{int(k,16):v for k,v in row['contexts'].items()})
                expected={int(k,16):v for k,v in row['native'].items()}
                for key in (0x6c0,0x6c4):self.assertEqual(actual_data[key],expected[key])
                for key in actual_scalars:self.assertEqual(actual_scalars[key],expected[key])
                self.assertEqual(actual_data[0x6b8],self.power.f32(data[0x6b8]))

    def test_option_entry_metadata_matches_independent_original_records(self):
        goldens=json.loads((REFERENCE/'native-option-metadata-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),136)
        for row in goldens['cases']:
            self.assertEqual(self.option_metadata.source_metadata(row['definition']),row['native'])
        for row in goldens['additional_native_controls']:
            definition=dict(TYPE=1,**row['definition'])
            self.assertEqual(self.option_metadata.source_metadata(definition),row['native'])

    def test_current_condition_definitions_all_match_original_property_body(self):
        goldens=json.loads((REFERENCE/'native-current-condition-source-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),639)
        for row in goldens['cases']:
            self.assertEqual(struct.pack('<I3f',*self.option_conditions.condition_input(row['definition'])),
                struct.pack('<I3f',*row['native']))

    def test_condition_append_retains_duplicates_without_phase_scaling(self):
        goldens=json.loads((REFERENCE/'native-condition-append-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),108)
        for row in goldens['cases']:
            actual=()
            for repeat in range(2):
                actual=self.option_conditions.append_condition(actual,tuple(row['source']),
                    source_line=row['source_line'],unit_line=row['unit_line'])
            self.assertEqual(actual,tuple(tuple(v)for v in row['native']))

    def test_ordinary_option_entry_uses_native_mode_and_resonance_boundaries(self):
        goldens=json.loads((REFERENCE/'native-ordinary-option-entry-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),128)
        for row in goldens['cases']:
            self.assertEqual(self.option_metadata.ordinary_entry(row['metadata'],
                resonance_level=row['resonance_level'],mode=row['mode']),row['native'])

    def snapshot_helpers(self, role_loader):
        return {'els_server.storage.character_schema':SimpleNamespace(character_uid=lambda uid:uid),
            'els_server.storage.item_actor':SimpleNamespace(require_active_character=lambda db,uid:None),
            'els_server.storage.seal_quests':SimpleNamespace(load_character=role_loader,current_slots=lambda db,c:(0,)*22),
            'els_server.storage.inventory_state':SimpleNamespace(load_items=lambda db,uid:
                [dict(uid=1,template=row[0],group=9,slot=1,count=1)for row in db.execute('SELECT template FROM equipped WHERE owner=?',(uid,))]),
            'els_server.domain.character_rules':SimpleNamespace(validate_career_state=lambda role:role)}

    def test_snapshot_keeps_role_and_items_at_one_external_commit_generation(self):
        # WAL is an isolated test-fixture choice so an external writer can
        # commit halfway through the reader. It never changes production mode.
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='native-attribute-test-') as directory:
            path=Path(directory)/'source.sqlite3'
            writer=sqlite3.connect(path)
            try:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.executescript('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER);'
                    'CREATE TABLE roles(uid INTEGER PRIMARY KEY,level INTEGER);'
                    'CREATE TABLE equipped(owner INTEGER,template INTEGER);'
                    'INSERT INTO character_owners VALUES(1001,2);INSERT INTO roles VALUES(1001,10);'
                    'INSERT INTO equipped VALUES(1001,111);')
                changed=[]
                def role(db,uid,account):
                    level=db.execute('SELECT level FROM roles WHERE uid=?',(uid,)).fetchone()[0]
                    if not changed:
                        with writer:
                            writer.execute('UPDATE roles SET level=20')
                            writer.execute('UPDATE equipped SET template=222')
                        changed.append(True)
                    return dict(uid=uid,level=level)
                with patch.dict(sys.modules,self.snapshot_helpers(role)):
                    first=self.snapshot.capture(path,1001,2)
                    second=self.snapshot.capture(path,1001,2)
                    with self.assertRaises(ValueError):self.snapshot.capture(path,1001,3)
                self.assertEqual((first['character']['level'],first['items'][0]['template']),(10,111))
                self.assertEqual((second['character']['level'],second['items'][0]['template']),(20,222))
                self.assertNotEqual(first['source_sha256'],second['source_sha256'])
            finally:writer.close()

    def test_capture_cannot_create_optional_schema_or_modify_player_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='native-attribute-test-') as directory:
            path=Path(directory)/'source.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.executescript('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER);'
                    'INSERT INTO character_owners VALUES(1001,2);')
            before=path.read_bytes()
            def unsafe_loader(db,uid,account):
                db.execute('CREATE TABLE unintended(value INTEGER)')
            with patch.dict(sys.modules,self.snapshot_helpers(unsafe_loader)),self.assertRaises(sqlite3.OperationalError):
                self.snapshot.capture(path,1001,2)
            self.assertEqual(path.read_bytes(),before)

    def test_all_original_conditional_power_types_and_epsilon_boundaries(self):
        cases=json.loads((REFERENCE/'native-conditional-power-goldens.json').read_bytes())['cases']
        self.assertEqual(len(cases),251)
        for index,row in enumerate(cases):
            fields={int(k,16):v for k,v in row['fields'].items()}
            contexts={int(k,16):v for k,v in row['contexts'].items()}
            expected={int(k,16):v for k,v in row['native'].items()}
            with self.subTest(index=index):
                actual=self.conditions.apply(fields,tuple(tuple(r)for r in row['conditions']),contexts)
                for offset,value in expected.items():
                    self.assertEqual(struct.pack('<f',actual[offset]),struct.pack('<f',value))

    def test_conditional_power_never_fills_a_missing_context_with_zero(self):
        fields={k:0. for k in self.conditions.FIELDS}
        contexts={k:0. for k in self.conditions.CONTEXTS}
        contexts.pop(0x3060)
        with self.assertRaises(ValueError):self.conditions.apply(fields,(),contexts)

    def test_naked_native_epsilon_is_preserved(self):
        result = self.passives.apply_naked((157000.,1202.,1202.,0.,0.,300.5,300.5),
            {106:1},self.definitions,pvp=False,extension5=0.,extension16=0.)
        self.assertEqual(struct.pack('<f',result[0]),struct.pack('<f',172700.015625))

    def test_composition_preserves_immutable_passive_basis(self):
        # Two source skills affect the same fields. Original 8978C0 does not
        # rebase percentages on a preceding passive's result.
        names = {'els_server.domain.native_passive_attributes':self.passives}
        for case in self.goldens['compositions']:
            ranks={int(k):v for k,v in case['owned'].items()}
            with self.subTest(pvp=case['phase_pvp']),patch.dict(sys.modules,names):
                actual = self.projection.compose(tuple(self.goldens['composition_basis']),
                    (0.,)*7,(0.,)*7,(0.,)*7,ranks,self.definitions,
                    {sid:(sid,rank)for sid,rank in ranks.items()},self.rules,
                    phase_pvp=case['phase_pvp'],unit_pvp=False,naked_extension5=0.,naked_extension16=0.,
                    flat_attack_extension=0.,flat_defense_extension=0.,extra_hp=0.)
                self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*case['native']))

    def test_invalid_rank_and_nonfinite_source_are_rejected(self):
        for rank in(True,-1,256):
            with self.subTest(rank=rank),self.assertRaises(ValueError):
                self.passives.apply_naked((1.,)*7,{106:rank},self.definitions,
                    pvp=False,extension5=0.,extension16=0.)
        for value in(math.inf,math.nan,1e40):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.equipment.merge_refinement((value,)*7,(0.,)*7,scale=None)

    def notification(self):
        w=self.wire
        return w.AttributeNotification(0,1,(),(0.,)*7,(0.,)*7,0,(),False,(),(),
                                       w.ProgressRecord(0,0,0,0),0.)

    def test_empty_wire_matches_original_107_byte_reader_contract(self):
        raw=self.wire.encode(self.notification())
        self.assertEqual(len(raw),107)
        self.assertEqual(raw,b'\0'+struct.pack('>Q',1)+bytes(98))

    def test_wire_preserves_native_signed_maps_and_utf16_byte_lengths(self):
        w=self.wire
        n=replace(self.notification(),named_options=((-128,(w.NamedOption(1,2,'中文','X',3),)),),
                  numeric_options=((127,((-1,2),)),))
        raw=w.encode(n)
        self.assertIn(struct.pack('>I',4)+'中文'.encode('utf-16le'),raw)
        self.assertIn(struct.pack('>bIii',127,1,-1,2),raw)

    def test_wire_refuses_implicit_or_ambiguous_state(self):
        changes=[dict(source_groups_enabled=1),dict(first_seven=(0.,)*6),
                 dict(named_options=((1,()),(1,()))),dict(power=math.nan),
                 dict(owner_uid=0),dict(equipment_changes=[])]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.wire.encode(replace(self.notification(),**change))


if __name__=='__main__':unittest.main()
