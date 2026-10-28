"""Portable original-native goldens; actual gameplay acceptance is separate."""
from dataclasses import replace
from contextlib import closing,ExitStack
from pathlib import Path
import importlib.util
import hashlib
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
        cls.equipment_classes = module('candidate_native_equipment_classes', 'els_server/domain/native_equipment_classes.py')
        with patch.dict(sys.modules,{'els_server.domain.native_equipment_classes':cls.equipment_classes}):
            cls.worn = module('candidate_native_worn', 'els_server/domain/native_worn_item_inputs.py')
        cls.set_conditions = module('candidate_native_set_conditions', 'els_server/domain/native_set_conditions.py')
        cls.set_sources = module('candidate_native_set_sources', 'els_server/domain/native_set_sources.py')
        cls.resonance_groups = module('candidate_native_resonance_groups', 'els_server/domain/native_resonance_source_groups.py')
        cls.pet_inputs = module('candidate_native_pet_inputs', 'els_server/domain/native_pet_attribute_inputs.py')
        cls.artifact_inputs = module('candidate_native_artifact_inputs', 'els_server/domain/native_artifact_attribute_inputs.py')
        cls.title_inputs = module('candidate_native_title_inputs', 'els_server/domain/native_title_attribute_inputs.py')
        cls.collection_inputs = module('candidate_native_collection_inputs', 'els_server/domain/native_collection_attribute_inputs.py')
        cls.world_buff_inputs = module('candidate_native_world_buff_inputs', 'els_server/domain/native_world_buff_attribute_inputs.py')
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
            cls.extended_maps = module('candidate_native_extended_maps', 'els_server/domain/native_extended_option_maps.py')
            cls.extended_inputs = module('candidate_native_extended_inputs', 'els_server/domain/native_extended_option_inputs.py')
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

    def test_fishing_tail_current_sources_and_positive_original_controls(self):
        goldens=json.loads((REFERENCE/'native-fishing-option-tail-goldens.json').read_bytes())
        path=REFERENCE/'els_server/domain/native_fishing_option_inputs.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),goldens['source_sha256'])
        self.set_sources.PROJECT_ROOT=ROOT
        with patch.dict(sys.modules,{'els_server.domain.native_worn_item_inputs':self.worn,
                                    'els_server.domain.native_set_sources':self.set_sources}):
            fishing=module('candidate_native_fishing_tail','els_server/domain/native_fishing_option_inputs.py')
            self.assertEqual(len(goldens['rows']),18)
            for row in goldens['rows']:
                source=goldens['inputs'][row['input']]
                actual=fishing.option_ids(tuple(source['items']),{int(k):v for k,v in source['bound'].items()},
                    {int(k):bytes.fromhex(v)for k,v in source['records'].items()},capacity=source['capacity'],
                    category77={int(k):v for k,v in source['category77'].items()},special_mode_level=source['special_mode_level'])
                self.assertEqual(actual,tuple(row['expected']),row['source_class'])
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
            args=dict(row['args']);args['precondition_skill_categories']={int(k):v for k,v in args['precondition_skill_categories'].items()}
            with self.subTest(index=index):
                actual=self.contexts.build_condition_contexts(tuple(row['resistances']),**args)
                self.assertEqual(actual,{int(k,16):v for k,v in row['native'].items()})

    def test_complete_second_option_map_phase_matches_original(self):
        goldens=json.loads((REFERENCE/'native-extended-option-maps-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),292)
        for index,row in enumerate(goldens['cases']):
            def decode(values,pair=False,tags=False):
                return {(tuple(k)if pair else int(k)):(tuple(v)if tags else v)for k,v in values}
            before=row['before'];args=dict(row['args'])
            for k in('skills','alternate_skills','category_rates','source_resistances'):
                args[k]=tuple(args[k])
            args['capability_fields']={int(k,16):v for k,v in args['capability_fields'].items()}
            args['factor_rows']=tuple(tuple(v)for v in args['factor_rows'])
            with self.subTest(index=index):
                actual=self.extended_maps.merge_extended_maps(decode(before[0]),decode(before[1]),
                    decode(before[2],pair=True),decode(before[3],tags=True),decode(before[4],tags=True),
                    tuple(before[5]),**args)
                values=row['native']
                self.assertEqual(actual,(decode(values[0]),decode(values[1]),decode(values[2],pair=True),
                    decode(values[3],tags=True),decode(values[4],tags=True),tuple(values[5])))

    def test_second_option_properties_match_original_source_reader(self):
        goldens=json.loads((REFERENCE/'native-extended-option-sources-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),84)
        for index,row in enumerate(goldens['cases']):
            expected=dict(row['native'])
            for key in('skills','alternate_skills','source_resistances'):expected[key]=tuple(expected[key])
            expected['capability_fields']={int(k,16):v for k,v in expected['capability_fields'].items()}
            with self.subTest(index=index):
                self.assertEqual(self.extended_inputs.extended_source_inputs(row['definition']),expected)

    def test_all_legal_careers_match_original_equipment_class_gate(self):
        goldens=json.loads((REFERENCE/'native-equipment-class-goldens.json').read_bytes())
        self.assertEqual(goldens['cases'],40170)
        bitmap=bytes.fromhex(goldens['acceptance_bits']);index=0
        for current in goldens['classes']:
            for required in goldens['required_classes']:
                actual=self.equipment_classes.class_eligible(required,current)
                self.assertEqual(actual,bool(bitmap[index//8]>>(index%8)&1),(required,current))
                index+=1
        with self.assertRaises(TypeError):self.equipment_classes.tables()[1]['stage']=99

    def test_worn_side_uses_native_equipment_slot_not_bag_group(self):
        goldens=json.loads((REFERENCE/'native-equipment-slot-goldens.json').read_bytes())
        self.assertEqual(len(goldens['cases']),74)
        for row in goldens['cases']:
            self.assertEqual(self.worn.slot_side(row['slot_code']),row['native'])

    def test_all_current_set_sources_reproduce_original_threshold_trace(self):
        goldens=json.loads((REFERENCE/'native-all-set-sources-goldens.json').read_bytes())
        source=self.set_sources.catalog();digest=hashlib.sha256();count=0
        self.assertEqual(len(source['definitions']),11422)
        for sid,d in sorted(source['definitions'].items()):
            if d['qualified']is None:
                thresholds={v[0]for v in d['ordinary']};qualifiers=(0,1)
            else:
                thresholds={v[0]&0xffffffff for v in d['qualified']}
                qualifiers=tuple(sorted({0,*[v[1]for v in d['qualified']]}))
            pieces={0,1,0xffffffff}
            for value in thresholds:
                for delta in(-1,0,1):
                    if 0<=value+delta<2**32:pieces.add(value+delta)
            for qualifier in qualifiers:
                for piece in sorted(pieces):
                    effects=self.set_conditions.select_effect_ids(d['ordinary'],d['qualified'],qualifier,piece)
                    digest.update(json.dumps([sid,qualifier,piece,effects],separators=(',',':')).encode()+b'\n');count+=1
        self.assertEqual(count,goldens['cases'])
        self.assertEqual(digest.hexdigest(),goldens['native_trace_sha256'])
        first=next(iter(source['definitions'].values()))
        with self.assertRaises(TypeError):first['ordinary']=()

    def test_current_pet_sources_reproduce_original_registration_and_collector_trace(self):
        self.pet_inputs.PROJECT_ROOT=ROOT
        source=self.pet_inputs.catalog();digest=hashlib.sha256();count=0
        proof=json.loads((REFERENCE/'native-pet-attribute-source-goldens.json').read_bytes())
        self.assertEqual(len(source),proof['templates'])
        for identity,definition in sorted(source.items()):
            for stage in range(len(definition['status'])):
                for satiety in(0,1919,1920,1921,4800):
                    for gear in({}, {2:dict(template=980035,socket=110323),1:dict(template=135974,socket=110200)}):
                        pet=dict(unit=identity,step=stage,satiety=satiety,equipment=gear)
                        for excluded in(False,True):
                            actual=self.pet_inputs.option_ids(pet,excluded=excluded)
                            digest.update(json.dumps([identity,stage,satiety,gear,excluded,actual],sort_keys=True,separators=(',',':')).encode()+b'\n');count+=1
        self.assertEqual(count,proof['cases'])
        self.assertEqual(digest.hexdigest(),proof['native_trace_sha256'])
        with self.assertRaises(TypeError):source[2]['auras']=()
        with self.assertRaises(ValueError):self.pet_inputs.decode((REFERENCE/'native-pet-attribute-sources.json').read_bytes()+b' ')
        with self.assertRaises(ValueError):self.pet_inputs.option_ids(dict(unit=50,step=0,satiety=3840),excluded=False)

    def test_current_artifact_sources_reproduce_original_stage_and_potential_controls(self):
        self.artifact_inputs.PROJECT_ROOT=ROOT
        proof=json.loads((REFERENCE/'native-artifact-attribute-source-goldens.json').read_bytes())
        for identity,stage,potentials,native in proof['rows']:
            self.assertEqual(self.artifact_inputs.option_ids(identity,stage,tuple(potentials)),tuple(native))
        self.assertEqual(len(proof['rows']),180)
        with self.assertRaises(TypeError):self.artifact_inputs.catalog()[1]=()
        with self.assertRaises(ValueError):self.artifact_inputs.option_ids(0,1,(0,0,0,0))
        with self.assertRaises(ValueError):self.artifact_inputs.decode((REFERENCE/'native-artifact-attribute-sources.json').read_bytes()+b' ')

    def test_all_current_titles_reproduce_original_property_and_lookup_trace(self):
        self.title_inputs.PROJECT_ROOT=ROOT
        proof=json.loads((REFERENCE/'native-title-attribute-source-goldens.json').read_bytes())
        source=self.title_inputs.catalog();digest=hashlib.sha256();count=0
        for identity,row in sorted(source.items()):
            hp,pa,ma,pd,md=row['flat'];expected=tuple(map(float,(hp,pa,ma,0,0,pd,md)))
            self.assertEqual(self.title_inputs.inputs(identity)['direct'],expected)
            for override in(identity,-1,0):
                options=self.title_inputs.inputs(identity if override else 0)['options']
                digest.update(json.dumps([identity,row['flat'],override,options],separators=(',',':')).encode()+b'\n');count+=1
        self.assertEqual(count,proof['cases'])
        self.assertEqual(digest.hexdigest(),proof['native_trace_sha256'])
        with self.assertRaises(TypeError):source[10]['options']=()
        with self.assertRaises(ValueError):self.title_inputs.decode((REFERENCE/'native-title-attribute-sources.json').read_bytes()+b' ')

    def test_all_current_collection_definitions_match_original_class_stage_lookup(self):
        self.collection_inputs.PROJECT_ROOT=ROOT
        proof=json.loads((REFERENCE/'native-collection-attribute-source-goldens.json').read_bytes())
        for career,stage,native in proof['rows']:
            self.assertEqual(self.collection_inputs.lookup(career,stage),tuple(native))
        self.assertEqual(len(proof['rows']),600)
        with self.assertRaises(TypeError):self.collection_inputs.catalog()[10,0]=()
        with self.assertRaises(ValueError):self.collection_inputs.decode((REFERENCE/'native-collection-attribute-sources.json').read_bytes()+b' ')

    def test_current_collection_DTO_active_gate_matches_complete_original_collector(self):
        self.collection_inputs.PROJECT_ROOT=ROOT
        proof=json.loads((REFERENCE/'native-collection-dto-source-goldens.json').read_bytes())
        for registered,active,native in proof['rows']:
            value=dict(active=active,registered=[registered],expiry=0,expansion=0,field1d=1,field21=1)
            self.assertEqual(self.collection_inputs.option_ids(value),tuple(native))
        self.assertEqual(len(proof['rows']),600)

    def test_all_world_BuffManager_sources_match_original_active_vector_getter(self):
        self.world_buff_inputs.PROJECT_ROOT=ROOT
        proof=json.loads((REFERENCE/'native-world-buff-attribute-source-goldens.json').read_bytes())
        for identity,repeats,native in proof['rows']:
            self.assertEqual(self.world_buff_inputs.option_ids((identity,)*repeats),tuple(native))
        self.assertEqual(len(proof['rows']),927)
        with self.assertRaises(TypeError):self.world_buff_inputs.catalog()[126]=()
        with self.assertRaises(ValueError):self.world_buff_inputs.option_ids((999999,))
        with self.assertRaises(ValueError):self.world_buff_inputs.decode((REFERENCE/'native-world-buff-attribute-sources.json').read_bytes()+b' ')

    def test_world_base_and_INT_sources_keep_original_collision_and_mixed_vector_order(self):
        self.world_buff_inputs.PROJECT_ROOT=ROOT
        proof=json.loads((REFERENCE/'native-world-buff-attribute-source-goldens-v2.json').read_bytes())
        self.assertEqual(len(self.world_buff_inputs.catalog()),383)
        self.assertEqual(proof['collisions'],[1540])
        for identities,native in proof['rows']:
            self.assertEqual(self.world_buff_inputs.option_ids(tuple(identities)),tuple(native))
        self.assertEqual(len(proof['rows']),1153)

    def test_106_resonance_groups_require_the_actual_selected_page(self):
        from copy import deepcopy
        ids=((1,2,4,16,17),(18,19,20,21,22),(11,12,13,14,15))
        groups=tuple((tab,tuple((sid,10 if sid==1 else 0)for sid in values))for tab,values in enumerate(ids))
        points=tuple(sorted(pair for tab,values in groups for pair in values))
        source=dict(account=dict(enabled=True,level=200,experience=12345),profile=dict(
            state=dict(selected_page=1,page_count=1,level=200,cumulative_experience=12345,allocation_groups=groups),
            pages=dict(selected_page=1,pages=(dict(page_id=1,points=points),))))
        self.assertEqual(self.resonance_groups.numeric_groups(source),groups)
        other=deepcopy(source);other['profile']['pages']['selected_page']=2
        with self.assertRaises(ValueError):self.resonance_groups.numeric_groups(other)
        other=deepcopy(source);other['profile']['pages']['pages'][0]['points']=tuple((s,0)for s,p in points)
        with self.assertRaises(ValueError):self.resonance_groups.numeric_groups(other)
        other=deepcopy(source);other['profile']=None
        with self.assertRaises(ValueError):self.resonance_groups.numeric_groups(other)
        self.assertEqual(self.resonance_groups.numeric_groups(dict(account=dict(enabled=False),profile=None)),())

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
            'els_server.storage.titles':SimpleNamespace(snapshot=lambda db,uid,now=None:dict(title=0,owned=[],missions=[]),completed_for_equipment=lambda db,uid:()),
            'els_server.storage.boosting_2026_force_inventory':SimpleNamespace(saved=lambda db,uid:()),
            'els_server.storage.boosting_2026_force_equipment':SimpleNamespace(saved=lambda db,uid:((0,0),)*3),
            'els_server.storage.avatar_sets':SimpleNamespace(snapshot=lambda db,uid:(0,())),
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

    def test_enabled_resonance_requires_saved_allocations_before_attribute_capture(self):
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='native-attribute-test-') as directory:
            path=Path(directory)/'source.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.executescript('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER);'
                    'CREATE TABLE account_resonance(account_id INTEGER,enabled INTEGER,experience INTEGER,revision INTEGER);'
                    'CREATE TABLE equipped(owner INTEGER,template INTEGER);'
                    'INSERT INTO character_owners VALUES(1001,2);'
                    'INSERT INTO account_resonance VALUES(2,1,50,1);')
            before=path.read_bytes()
            role=lambda db,uid,account:dict(uid=uid,level=99)
            with patch.dict(sys.modules,self.snapshot_helpers(role)),\
                 patch('els_server.storage.resonance_state.limit',return_value=1000),\
                 patch('els_server.storage.resonance_state.level',return_value=200):
                with self.assertRaisesRegex(ValueError,'synchronized character pages'):
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
                    flat_attack_extension=0.,flat_defense_extension=0.,extra_hp=0.,title_direct=(0.,)*7)
                self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*case['native']))

    def test_invalid_rank_and_nonfinite_source_are_rejected(self):
        for rank in(True,-1,256):
            with self.subTest(rank=rank),self.assertRaises(ValueError):
                self.passives.apply_naked((1.,)*7,{106:rank},self.definitions,
                    pvp=False,extension5=0.,extension16=0.)
        for value in(math.inf,math.nan,1e40):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.equipment.merge_refinement((value,)*7,(0.,)*7,scale=None)

    def test_current_title_direct_fields_follow_native_basis_addition(self):
        evidence=json.loads((REFERENCE/'native-title-composition-order-goldens.json').read_bytes())
        self.assertEqual(evidence['cases'],546)
        self.assertEqual(evidence['positive_current_titles'],182)
        # Historical888CA0 proof is retained unchanged; the new896870 proof
        # below pins the expanded module while replaying this same wire phase.
        self.assertEqual(evidence['source_sha256'],'807d5ac498b4564295601c12bcd3ceb94b9c74c233b4c6bbe98eae309eec5b05')
        names={'els_server.domain.native_passive_attributes':self.passives}
        with patch.dict(sys.modules,names):
            for row in evidence['rows']:
                actual=self.projection.compose(tuple(row['base']),tuple(row['equipped']),
                    tuple(row['options']),tuple(row['learned']),{},{},{},(),
                    phase_pvp=False,unit_pvp=False,naked_extension5=0.,naked_extension16=0.,
                    flat_attack_extension=0.,flat_defense_extension=0.,extra_hp=row['extra_hp'],
                    title_direct=tuple(row['title_direct']))
                self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*row['native']))

    def test_power_basis_uses_its_own_original_addition_order(self):
        evidence=json.loads((REFERENCE/'native-power-composition-order-goldens.json').read_bytes())
        self.assertEqual(evidence['cases'],546)
        self.assertEqual(evidence['different_from_wire'],364)
        self.assertEqual(hashlib.sha256(Path(self.projection.__file__).read_bytes()).hexdigest(),evidence['source_sha256'])
        with patch.dict(sys.modules,{'els_server.domain.native_passive_attributes':self.passives}):
            for row in evidence['rows']:
                actual=self.projection.compose_power(tuple(row['base']),tuple(row['equipped']),
                    tuple(row['options']),tuple(row['learned']),{},{},{},(),
                    phase_pvp=False,unit_pvp=False,naked_pvp=False,naked_extension5=0.,naked_extension16=0.,
                    flat_attack_extension=0.,flat_defense_extension=0.,extra_hp=row['extra_hp'],
                    title_direct=tuple(row['title_direct']))
                self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*row['native']))

    def test_power_naked_mode_is_independent_from_wire_phase_mode(self):
        with patch.dict(sys.modules,{'els_server.domain.native_passive_attributes':self.passives}):
            for row in self.goldens['cases']:
                if row['phase']!='naked':continue
                ranks={int(k):v for k,v in row['query_ranks'].items()}
                actual=self.projection.compose_power(tuple(self.goldens['basis']),
                    (0.,)*7,(0.,)*7,(0.,)*7,ranks,self.definitions,{},(),
                    phase_pvp=not row['pvp'],unit_pvp=False,naked_pvp=row['pvp'],
                    naked_extension5=0.,naked_extension16=0.,flat_attack_extension=0.,
                    flat_defense_extension=0.,extra_hp=0.,title_direct=(0.,)*7)
                self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*row['native']))

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

    def test_original_option_color_profiles_and_missing_records(self):
        source=module('candidate_option_colors','els_server/domain/native_option_colors.py')
        raw=(REFERENCE/'native-option-color-sources.json').read_bytes()
        catalog=source.decode(raw)
        golden=json.loads((REFERENCE/'native-option-color-source-goldens.json').read_bytes())
        self.assertEqual(len(catalog),70522)
        self.assertEqual(len(golden['rows']),288)
        for row in golden['rows']:
            self.assertEqual(catalog[row['id']],tuple(row['fields']))
        identity=golden['rows'][0]['id']
        self.assertEqual(source.colors((identity,-1,identity),3,catalog),
                         (catalog[identity][3],None,catalog[identity][3]))
        with self.assertRaises(TypeError):catalog[identity]=(0,)*6
        with self.assertRaises(ValueError):source.decode(raw+b' ')

    def test_all_native_item_constructor_option_vectors(self):
        source=module('candidate_option_vectors','els_server/domain/native_item_option_vectors.py')
        golden=json.loads((REFERENCE/'native-item-option-vector-source-goldens.json').read_bytes())
        types={101+i:v for i,v in enumerate((802,803,804,805,806,807))}
        self.assertEqual(len(golden['rows']),71)
        for row in golden['rows']:
            actual=source.project(tuple(tuple(v)for v in row['groups']),types,mutations=())
            for offset,values in row['vectors'].items():
                self.assertEqual(actual[int(offset,16)],tuple(values))
            self.assertEqual(actual[0x1e0],row['spirit_group'])
            self.assertEqual(actual[0x190],tuple(tuple(v)for v in row['engraving']))
            self.assertEqual(actual[0x158],{int(k):tuple(v)for k,v in row['skill_groups'].items()})
        with self.assertRaises(ValueError):source.project(((),)*33,types,mutations=((1,2),))
        with self.assertRaises(ValueError):source.project(((),)*28+((1,)*17,)+((),)*4,types,mutations=())

    def test_whole_native_post_power_eligibility_and_rounding(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_post_power','els_server/domain/native_post_power_passives.py')
        golden=json.loads((REFERENCE/'native-post-power-whole-phase-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),200)
        for row in golden['rows']:
            inputs={sid:dict(eligible=bool(row['mask']&(1<<i)),
                parameters=source.project_definition(golden['source_definitions'][str(sid)],row['rank']))
                for i,sid in enumerate(source.FIELDS)}
            current={int(k,16):v for k,v in row['current'].items()}
            actual=source.apply_qualified(current,inputs,row['power'])['raw_fields']
            self.assertEqual(actual,{int(k,16):v for k,v in row['native'].items()})
            self.assertEqual(current,{int(k,16):v for k,v in row['current'].items()})


    def test_current_factor_profiles_and_native_append_boundaries(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_factor_inputs','els_server/domain/native_option_factor_inputs.py')
        for filename,count in(('native-option-factor-source-goldens-v2.json',833),
                               ('native-option-factor-boundary-goldens-v2.json',33)):
            golden=json.loads((REFERENCE/filename).read_bytes())
            self.assertEqual(len(golden['rows']),count)
            if 'source_sha256'in golden:self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
            for row in golden['rows']:
                with self.subTest(file=filename,identity=row['definition']['ID']):
                    actual=source.capability_rows(row['definition'])
                    self.assertEqual(len(actual),len(row['native']))
                    for (kind,value),(native_kind,native_value)in zip(actual,row['native']):
                        self.assertEqual(kind,native_kind)
                        self.assertEqual(struct.pack('<f',value),struct.pack('<f',native_value))

    def test_current_capability_sources_through_whole_native_second_merge(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            factor=module('candidate_capability_factor','els_server/domain/native_option_factor_inputs.py')
        golden=json.loads((REFERENCE/'native-current-capability-source-chain-goldens-v2.json').read_bytes())
        self.assertEqual(len(golden['rows']),46)
        self.assertEqual(set(golden['capability_types']),set(self.extended_maps.CAPABILITY_TYPES))
        for row in golden['rows']:
            definition=row['definition']
            args=self.extended_inputs.extended_source_inputs(definition)
            scalars=self.option_scalars.scalar_inputs(definition)
            args.update(category_rates=tuple(scalars[o]for o in(0x3e8,0x3ec,0x3f0,0x3f4)),
                factor_rows=factor.capability_rows(definition),weight=row['weight'],resistances=(0,)*7)
            actual=self.extended_maps.merge_extended_maps({}, {}, {}, {}, {},**args)
            expected=[]
            for i,values in enumerate(row['native'][:5]):
                expected.append({tuple(k)if i==2 else k:tuple(v)if i in(3,4)else v for k,v in values})
            expected.append(tuple(row['native'][5]))
            self.assertEqual(actual,tuple(expected))


    def test_whole_native_max_mp_sources_and_float_order(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_max_mp','els_server/domain/native_max_mp_inputs.py')
        golden=json.loads((REFERENCE/'native-max-mp-whole-goldens-v2.json').read_bytes())
        self.assertEqual(len(golden['rows']),414)
        for row in golden['rows']:
            phase={int(k):v for k,v in row['phase_values'].items()}
            unit={int(k):v for k,v in row['unit_values'].items()}
            rank=5 if row['label']=='all-rank5'else 1
            owned=source.PHASE_SKILLS|source.UNIT_SKILLS if row['label'].startswith('all-')else {int(row['label'])}if row['label']!='none'else set()
            for values,pvp in((phase,row['mode']),(unit,False)):
                for sid,value in values.items():
                    actual=self.passives.parameter(golden['source_definitions'][str(sid)],'SA_MAX_MP_ABS',rank,
                        pvp=pvp,direct=True,default=0.)if sid in owned else 0.
                    self.assertEqual(struct.pack('<f',actual),struct.pack('<f',value))
            actual=source.maximum(phase,unit,**{k:row[k]for k in('worn','flat','rate','extension5','extension17')})
            self.assertEqual(struct.pack('<f',actual),struct.pack('<f',row['native']))
        with self.assertRaises(ValueError):source.maximum({},unit,worn=0.,flat=0.,rate=0.,extension5=0.,extension17=0.)

    def test_native_mp_item_selector_is_distinct_from_general_worn_selector(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_mp_items','els_server/domain/native_max_mp_inputs.py')
        golden=json.loads((REFERENCE/'native-equipment-mp-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),534)
        with patch.dict(sys.modules,{'els_server.domain.native_worn_item_inputs':self.worn}):
            for row in golden['rows']:
                actual=source.equipment_mp(*(tuple(row[k])for k in('worn','excluded','added')),
                    selector=row['selector'],mode_side=row['mode_side'])
                self.assertEqual(struct.pack('<f',actual),struct.pack('<f',row['native']))
            with self.assertRaises(ValueError):source.equipment_mp((None,),(),(),selector=0,mode_side=False)
            with self.assertRaises(ValueError):source.equipment_mp((),(),({'template_present':False},),selector=0,mode_side=False)
        for value in(0.,5.,20.,30.):
            record=bytearray(232);struct.pack_into('<f',record,0x28,value)
            self.assertEqual(source.template_mp(bytes(record)),value)


    def test_whole_mp_chain_with_current_worn_and_selected_erp(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_mp_composed','els_server/domain/native_max_mp_inputs.py')
        golden=json.loads((REFERENCE/'native-max-mp-composed-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),96)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        erp={int(k):tuple(v)for k,v in golden['ERP_definitions'].items()}
        worn=tuple(golden['worn'])
        with patch.dict(sys.modules,{'els_server.domain.native_worn_item_inputs':self.worn}):
            for row in golden['rows']:
                definitions=golden['source_definitions'];rank=row['rank']
                phase={sid:self.passives.parameter(definitions[str(sid)],'SA_MAX_MP_ABS',rank,pvp=row['mode'],direct=True,default=0.)for sid in source.PHASE_SKILLS}
                unit={sid:self.passives.parameter(definitions[str(sid)],'SA_MAX_MP_ABS',rank,pvp=False,direct=True,default=0.)for sid in source.UNIT_SKILLS}
                replacements=(worn[0],)if row['replace']else()
                item_mp=source.equipment_mp(worn,replacements,replacements,selector=row['selector'],mode_side=False)
                points={int(k):v for k,v in row['points'].items()}
                e5=self.extension.contribution(points,tuple(row['override']),erp,5,0,1.)
                e17=self.extension.contribution(points,tuple(row['override']),erp,17,0,1.)
                actual=source.maximum(phase,unit,worn=item_mp,flat=row['flat'],rate=row['rate'],extension5=e5,extension17=e17)
                self.assertEqual(struct.pack('<f',actual),struct.pack('<f',row['native']))


    def test_native_activated_set_power_source_preserves_double_and_unique_order(self):
        source=module('candidate_set_power','els_server/domain/native_set_power_factor.py')
        raw=(REFERENCE/'native-set-power-factor-sources.json').read_bytes();coefficients=source.decode(raw)
        golden=json.loads((REFERENCE/'native-set-power-factor-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),128)
        self.assertEqual(len(golden['leaf_rows']),8)
        definitions=self.set_sources.catalog()['definitions']
        for row in golden['leaf_rows']:
            value=source.factor(tuple(row['active_ids']),coefficients)
            self.assertEqual(struct.pack('<d',value),struct.pack('<d',row['native']))
        with patch.dict(sys.modules,{'els_server.domain.native_set_conditions':self.set_conditions}):
            for row in golden['rows']:
                active=source.active_sets({int(k):tuple(v)for k,v in row['pieces'].items()},definitions)
                self.assertEqual(active,tuple(row['active_ids']))
                self.assertEqual(struct.pack('<d',source.factor(active,coefficients)),struct.pack('<d',row['native']))
        with self.assertRaises(TypeError):coefficients[20004]=9.9
        with self.assertRaises(ValueError):source.decode(raw+b' ')
        self.assertNotEqual(struct.pack('<d',coefficients[20004]),struct.pack('<d',self.power.f32(1.2)))

    def test_current_native_class_registry_and_all_class_power_branches(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_class_power','els_server/domain/native_class_power_inputs.py')
        golden=json.loads((REFERENCE/'native-class-power-source-goldens.json').read_bytes())
        types=source.project(golden['source'])
        self.assertEqual(dict(types),{int(k):v for k,v in golden['native_types'].items()})
        self.assertEqual(len(types),120)
        self.assertEqual(len(golden['rows']),585)
        for row in golden['rows']:
            kind=source.kind(row['class_id'],types);self.assertEqual(kind,row['kind'])
            value=(row['physical']if kind==1 else row['magical']if kind==2 else max(row['physical'],row['magical']))*.4+1.
            self.assertEqual(struct.pack('<d',value),struct.pack('<d',row['native_factor']))
        # The original source compares float32 coefficients, with equality2.
        tied=source.project({'1':{'1':999,'2':100.00000001,'4':100.}})
        self.assertEqual(tied[999],2)
        self.assertIsNone(source.kind(1,types))
        with self.assertRaises(TypeError):types[1]=1


    def test_canonical_item_options_follow_native_source_order_and_all_gates(self):
        source=module('candidate_item_option_collect','els_server/domain/native_item_attribute_options.py')
        vectors=module('candidate_item_option_vector_collect','els_server/domain/native_item_option_vectors.py')
        golden=json.loads((REFERENCE/'native-item-attribute-option-goldens-v2.json').read_bytes())
        self.assertEqual(len(golden['rows']),277)
        types={101+i:v for i,v in enumerate((802,803,804,805,806,807))}
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        tail=dict(wire_hex=golden['canonical_seed_tail'],fields=[dict(offset='0x3ec',wire_offset=0)])
        self.assertEqual({r['canonical_trailing_state']for r in golden['rows']},{source.circuit_state_from_seed(tail)})
        for row in golden['rows']:
            groups=tuple(tuple(v)for v in row['groups'])
            properties=tuple((v,0,0,0,0,0)for v in row['property_keys'])
            projected=vectors.project(groups,types,mutations=())
            args={k:row[k]for k in('character_level','template_level','allow26','allow27','circuit_state')}
            options,level=source.collect(projected,properties,(501,501,0,502),**args)
            self.assertEqual(options,tuple(row['native_options']))
            self.assertEqual(level,row['native_level'])
        record=bytearray(232);record[0xd1]=80
        self.assertEqual(source.template_level(bytes(record)),80)
        with self.assertRaises(ValueError):source.template_level(bytes(231))
        for key,value in(('allow26',1),('allow27',None),('circuit_state',-1),('character_level',-1),('template_level',256)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                source.collect(projected,properties,(),**dict(args,**{key:value}))


    def test_native_pre_merge_scaling_retains_unscaled_leaves_and_signed_zero(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_scalar_merge':self.option_merge}):
            source=module('candidate_pre_scale','els_server/domain/native_option_pre_scale.py')
        golden=json.loads((REFERENCE/'native-option-pre-scale-goldens.json').read_bytes())
        scalars={int(k,16):v for k,v in golden['source'].items()};data=tuple(golden['source_data'])
        self.assertEqual(len(golden['rows']),6)
        for row in golden['rows']:
            values,actual_data=source.transform(scalars,data,row['coefficient'])
            for k,v in values.items():self.assertEqual(struct.pack('<f',v),struct.pack('<f',row['native'][hex(k)]))
            self.assertEqual(struct.pack('<13f',*actual_data),struct.pack('<13f',*row['native_data']))
        self.assertIn(0x11c,source.COPIED)
        with self.assertRaises(ValueError):source.transform({},data,1.)

    def ordinary_subset_source(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_scalar_merge':self.option_merge}):
            pre=module('candidate_callback_pre_scale','els_server/domain/native_option_pre_scale.py')
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_pre_scale':pre,
            'els_server.domain.native_option_metadata':self.option_metadata,
            'els_server.domain.native_option_record_merge':self.option_record}):
            return module('candidate_ordinary_subset','els_server/domain/native_ordinary_option_subset.py')

    def test_whole_ordinary_option_callback_scalar_data_branches(self):
        source=self.ordinary_subset_source()
        golden=json.loads((REFERENCE/'native-ordinary-option-subset-goldens-v2.json').read_bytes())
        before={int(k,16):v for k,v in golden['base'].items()}
        inputs={int(k,16):v for k,v in golden['source'].items()}
        self.assertEqual(len(golden['rows']),154)
        for row in golden['rows']:
            meta=source.metadata(row['definition'])
            actual,data=source.merge(before,inputs,tuple(golden['before_data']),tuple(golden['source_data']),meta,**row['args'])
            for k,v in actual.items():self.assertEqual(struct.pack('<f',v),struct.pack('<f',row['native'][hex(k)]))
            self.assertEqual(struct.pack('<13f',*data),struct.pack('<13f',*row['native_data']))
        with self.assertRaises(ValueError):source.metadata(dict(m_iAddLevel=2**31))

    def test_whole_ordinary_callback_power_maps_follow_rank_and_level_branches(self):
        source=self.ordinary_subset_source()
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_metadata':self.option_metadata,
            'els_server.domain.native_option_power_maps':self.option_power_maps,
            'els_server.domain.native_option_condition_inputs':self.option_conditions}):
            maps=module('candidate_ordinary_maps','els_server/domain/native_ordinary_option_power_maps.py')
        golden=json.loads((REFERENCE/'native-ordinary-option-subset-goldens-v2.json').read_bytes())
        inputs=self.option_power_maps.source_map_inputs(golden['map_definition'])
        condition=self.option_conditions.condition_input(golden['map_definition'])
        for row in golden['rows']:
            args={k:v for k,v in row['args'].items()if k!='level'}
            actual=maps.merge({}, {}, (0,0.), (),inputs,condition,source.metadata(row['definition']),**args)
            expected=({k:v for k,v in row['native_maps'][0]},
                {tuple(k):v for k,v in row['native_maps'][1]},
                tuple(row['native_maps'][2]),tuple(tuple(v)for v in row['native_maps'][3]))
            self.assertEqual(actual,expected)

    def test_all_current_rank_level_profiles_feed_original_callback(self):
        source=self.ordinary_subset_source()
        golden=json.loads((REFERENCE/'native-current-ordinary-source-goldens.json').read_bytes())
        self.assertEqual(sum(v['definitions']for v in golden['profiles']),70522)
        self.assertEqual(len(golden['profiles']),5);self.assertEqual(len(golden['rows']),20)
        for row in golden['rows']:
            d=row['definition'];scalars=self.option_scalars.scalar_inputs(d)
            inputs={k:scalars[k]for k in self.option_merge.FIELDS}
            source_data=tuple(scalars[k]for k in(0x6b8,0x6bc,0x6c0,0x6c4,0x6c8,0x6cc))+self.option_data.direct_option_stats(d.get('STAT',{}))
            actual,data=source.merge(dict.fromkeys(self.option_merge.FIELDS,0.),inputs,(0.,)*13,source_data,source.metadata(d),**row['args'])
            for k,v in actual.items():self.assertEqual(struct.pack('<f',v),struct.pack('<f',row['native'][hex(k)]))
            self.assertEqual(struct.pack('<13f',*data),struct.pack('<13f',*row['native_data']))


    def test_native_probability_direction_defaults_to_one_including_lua_nil(self):
        golden=json.loads((REFERENCE/'native-probability-direction-default-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),32)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(self.option_power_maps.__file__).read_bytes()).hexdigest())
        for row in golden['rows']:
            source=self.option_power_maps.source_map_inputs(row['definition'])
            actual=self.option_power_maps.merge_map_inputs({}, {}, (0,0.),source,**row['args'])[1]
            self.assertEqual(actual,{tuple(k):v for k,v in row['native']})
            flag=row['definition'].get('m_bIncreaseDmgEnemyHPFew_IsDown')
            self.assertEqual({key[1]for key in source['probability']},{1 if flag is None else flag})


    def learned_stat_modules(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            loader=module('candidate_skill_stat_inputs','els_server/domain/native_skill_stat_inputs.py')
            with patch.dict(sys.modules,{'els_server.domain.native_skill_stat_inputs':loader}):
                collector=module('candidate_learned_stat_phase','els_server/domain/native_learned_stat_phase.py')
        return loader,collector

    def test_current_skill_stat_profiles_and_complete_three_channel_collector(self):
        loader,collector=self.learned_stat_modules()
        golden=json.loads((REFERENCE/'native-learned-stat-phase-goldens.json').read_bytes())
        self.assertEqual(golden['current_source_counts'],dict(total=4483,with_stat=4))
        self.assertEqual(len(golden['parser']),9)
        self.assertEqual(len(golden['rows']),63)
        for source in(loader,collector):
            self.assertEqual(hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest(),
                golden['source_sha256'][Path(source.__file__).stem])
        for row in golden['parser']:
            actual=loader.load(row['definition'])
            self.assertEqual(b''.join(struct.pack('<13f',*v)for v in actual),
                b''.join(struct.pack('<13f',*v)for v in row['native']))
        definitions={int(k):v for k,v in golden['definitions'].items()}
        for row in golden['rows']:
            actual=collector.collect(definitions,tuple(map(tuple,row['main'])),
                tuple(tuple(map(tuple,p))for p in row['presets']),row['selected_index'],tuple(map(tuple,row['extra'])))
            self.assertEqual(struct.pack('<13f',*actual),struct.pack('<13f',*row['native']),row['label'])

    def test_learned_stat_missing_presets_skip_extra_but_empty_selected_map_allows_it(self):
        _,collector=self.learned_stat_modules()
        definitions={1:dict(m_eType=1,m_Stat=dict(m_BaseHP={'1':7.}))}
        self.assertEqual(collector.collect(definitions,(),(),0,((1,1),)),(0.,)*13)
        self.assertEqual(collector.collect(definitions,(),((),),1,((1,1),)),(0.,)*13)
        self.assertEqual(collector.collect(definitions,(),((),),0,((1,1),))[6],7.)
        for main in(((1,0),),((1,2),)):
            with self.assertRaises(ValueError):collector.collect(definitions,main,((),),0,())
        self.assertEqual(collector.collect(definitions,((1,31),),((),),0,()),(0.,)*13)
        with self.assertRaises(ValueError):collector.collect(definitions,((1,1),(1,1)),(),0,())
        with self.assertRaises(ValueError):collector.collect({},((1,1),),(),0,())


    def test_original_integer_MP_option_scaling_and_truncation(self):
        ordinary=self.ordinary_subset_source()
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_metadata':self.option_metadata}):
            source=module('candidate_option_max_mp','els_server/domain/native_option_max_mp.py')
        golden=json.loads((REFERENCE/'native-option-max-mp-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),132)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        for row in golden['rows']:
            actual=source.merge(row['before'],source.source_value(row['definition']),
                ordinary.metadata(row['definition']),**row['args'])
            self.assertEqual(actual,row['native'])
        self.assertEqual(source.source_value({}),0)
        self.assertEqual(source.source_value({'m_iAddMpValue':None}),0)
        self.assertEqual(source.truncate(2147483647),-2147483648)
        with self.assertRaises(ValueError):source.source_value({'m_iAddMpValue':1.5})


    def test_all_current_reforge_sources_match_complete_original_getter(self):
        from els_server.domain import equipment_reforge_rules as source
        golden=json.loads((REFERENCE/'native-reforge-stat-source-goldens.json').read_bytes())
        raw=(ROOT/'els_server/data/equipment_reforge.json').read_bytes();policy=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),golden['policy_sha256'])
        self.assertEqual(golden['registrations'],84)
        self.assertEqual(golden['whole_getter_cases'],8118)
        self.assertEqual(len(golden['bindings']),369)
        with patch.object(source,'catalog',return_value=policy),patch.object(source,'require_target',
                side_effect=lambda identity:policy['targets'][str(identity)]):
            for row in golden['bindings']:
                self.assertEqual(policy['targets'][str(row['template'])]['record_sha256'],row['record_sha256'])
                for level in range(22):
                    actual=source.cumulative_stats(row['template'],level)
                    native=golden['native_profiles'][str(row['reforge_class'])][str(level)]
                    self.assertEqual(struct.pack('<7f',*actual),struct.pack('<7f',*native))


    def test_106_wire_matches_original_refresh_core_controls(self):
        golden=json.loads((REFERENCE/'native-106-refresh-core-goldens-v2.json').read_bytes())
        self.assertEqual(golden['cases'],28)
        self.assertEqual(golden['encoder_sha256'],hashlib.sha256(Path(self.wire.__file__).read_bytes()).hexdigest())
        for row in golden['rows']:
            notice=self.wire.AttributeNotification(0,1001,(),tuple(golden['first']),tuple(golden['second']),
                0,(),False,(),(),self.wire.ProgressRecord(0,0,0,0),row['wire_power'])
            self.assertEqual(hashlib.sha256(self.wire.encode(notice)).hexdigest(),row['wire_sha256'])
            selected=int(row['side']==1)if row['selector']==2 else int(row['selector']!=0)
            self.assertEqual(row['selected_record'],selected)
            maximum=(golden['first'],golden['second'])[selected][0]
            self.assertEqual(row['after'],dict(current=min(row['before']['current'],maximum),maximum=maximum))
            value=struct.unpack('<f',struct.pack('<f',row['wire_power']))[0]
            rounded=math.floor(struct.unpack('<f',struct.pack('<f',value+.5))[0])
            self.assertEqual(row['native_cached_power'],rounded)

    def test_106_progress_preserves_canonical_ERP_opaque_fields(self):
        golden=json.loads((REFERENCE/'native-resonance-progress-goldens.json').read_bytes())
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(self.resonance_groups.__file__).read_bytes()).hexdigest())
        ids=((1,2,4,16,17),(18,19,20,21,22),(11,12,13,14,15))
        groups=tuple((tab,tuple((sid,0)for sid in values))for tab,values in enumerate(ids))
        points=tuple(sorted(pair for tab,values in groups for pair in values))
        for row in golden['rows']:
            state=dict(selected_page=1,page_count=1,level=200,cumulative_experience=12345,
                allocation_groups=groups,**dict(zip(('field21','field25','field29','field31'),row['fields'])))
            source=dict(account=dict(enabled=True,level=200,experience=12345),profile=dict(state=state,
                pages=dict(selected_page=1,pages=(dict(page_id=1,points=points),))))
            fields=self.resonance_groups.progress_fields(source)
            self.assertEqual(fields,tuple(row['native']))
            notice=self.wire.AttributeNotification(0,1001,(),(1.,)*7,(2.,)*7,0,(),False,(),groups,
                self.wire.ProgressRecord(*fields),1.)
            self.assertEqual(hashlib.sha256(self.wire.encode(notice)).hexdigest(),row['wire_sha256'])
            for name,bad in(('field21',2**31),('field25',-2**31-1),('field29',-1),('field31',256)):
                good=state.pop(name)
                with self.assertRaises(ValueError):self.resonance_groups.progress_fields(source)
                state[name]=bad
                with self.assertRaises(ValueError):self.resonance_groups.progress_fields(source)
                state[name]=good
        self.assertEqual(self.resonance_groups.progress_fields(dict(account=dict(enabled=False),profile=None)),(0,0,0,0))


    def test_source_ordered_combined_option_pipeline_matches_both_original_callbacks(self):
        import els_server.domain as domain
        names=('native_power_kernel','native_option_scalar_inputs','native_option_scalar_merge',
            'native_option_data_merge','native_option_record_merge','native_option_pre_scale',
            'native_option_metadata','native_ordinary_option_subset','native_option_power_maps',
            'native_option_condition_inputs','native_ordinary_option_power_maps','native_option_factor_inputs',
            'native_extended_option_inputs','native_extended_option_maps','native_option_max_mp','native_option_fixed_hp','native_option_collector')
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in names:
                source=module('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,source,create=True))
            golden=json.loads((REFERENCE/'native-combined-option-pipeline-goldens-v2.json').read_bytes())
            self.assertEqual(len(golden['rows']),16)
            # Retain the original v2 traces for the existing leaves; fixed_HP
            # is separately qualified against the whole callback below.
            def decode(rows):return {tuple(k)if isinstance(k,list)else k:v for k,v in rows}
            for row in golden['rows']:
                inputs=tuple(source.OptionSource(tuple(s['option_ids']),s['level'],s['condition_value'],
                    s['rank_factor'],s['weight'])for s in row['sources'])
                definitions={int(k):v for k,v in row['definitions'].items()}
                initial=dict(row['initial']);initial['damage']=decode(initial['damage']);initial['alternate']=decode(initial['alternate'])
                initial['resistances']=tuple(initial['resistances'])
                actual=source.collect_ordinary(inputs,definitions,**row['args'])|source.collect_extended(inputs,definitions,initial,**row['args'])
                native=row['native']
                for k,v in actual['scalars'].items():
                    self.assertEqual(struct.pack('<f',v),struct.pack('<f',native['scalars'][hex(k)]))
                self.assertEqual(struct.pack('<13f',*actual['data']),struct.pack('<13f',*native['data']))
                self.assertEqual(actual['integer_MP'],native['integer_MP'])
                for name in('capabilities','probability','damage','alternate','extended_capabilities'):
                    self.assertEqual(actual[name],decode(native[name]))
                self.assertEqual(actual['resistances'],tuple(native['resistances']))
            for invalid in([], (source.OptionSource((1,),256,0,0.,1.),),
                (source.OptionSource((1,),1,0,0.,float('inf')),)):
                with self.assertRaises(ValueError):source.collect(invalid,{},mode=0,resonance_level=0,unit_line=0)


    def test_composed_aggregate_matches_original_nonempty_ERP_and_condition_stages(self):
        import els_server.domain as domain
        names=('native_power_kernel','native_option_scalar_inputs','native_option_scalar_merge',
            'native_option_data_merge','native_option_record_merge','native_option_pre_scale',
            'native_option_metadata','native_ordinary_option_subset','native_option_power_maps',
            'native_option_condition_inputs','native_ordinary_option_power_maps','native_option_factor_inputs',
            'native_extended_option_inputs','native_extended_option_maps','native_option_max_mp','native_option_fixed_hp','native_option_collector',
            'native_extension_inputs','native_resonance_attributes','native_cooldown_map','native_power_slopes',
            'native_power_normalization','native_condition_contexts','native_conditional_power_attributes',
            'native_max_mp_inputs','native_power_aggregation')
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in names:
                source=module('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,source,create=True))
            golden=json.loads((REFERENCE/'native-power-aggregation-composed-goldens.json').read_bytes())
            self.assertEqual(len(golden['rows']),4)
            self.assertEqual(golden['source_sha256'],'f6796d3ab7b912227b9ac7e700882c786f1c4164ed5a01e7df90e17ba962e244')
            for row in golden['rows']:
                args=dict(row['args'])
                for name in('resonance_points','resonance_definitions','phase_mp_values','unit_mp_values'):
                    args[name]={int(k):v for k,v in args[name].items()}
                args['resonance_definitions']={k:tuple(v)for k,v in args['resonance_definitions'].items()}
                for name in('resonance_override','condition_resistances'):args[name]=tuple(args[name])
                callbacks=tuple(domain.native_option_collector.OptionSource(tuple(s['option_ids']),s['level'],
                    s['condition_value'],s['rank_factor'],s['weight'])for s in row['sources'])
                actual=source.assemble(tuple(row['seven']),callbacks,{int(k):v for k,v in row['definitions'].items()},**args)
                self.assertEqual(struct.pack('<2f',*actual['power']),struct.pack('<2f',*row['native_power']))
                expected=dict(row['native_arguments'])
                for name in('stat_fields','data_fields'):expected[name]={int(k,16):v for k,v in expected[name].items()}
                expected['maps']={int(k,16):{tuple(key)if isinstance(key,list)else key:v for key,v in values}
                    for k,values in expected['maps'].items()}
                self.assertEqual(actual['arguments'],expected)
            # Retain all former non-LuCiel controls and pin the expanded files
            # with the new selector2 original-source proof.
            common=json.loads((REFERENCE/'native-luciel-shared-hp-goldens.json').read_bytes())
            for name,sha in common['source_sha256'].items():
                self.assertEqual(hashlib.sha256((REFERENCE/'els_server/domain'/(name+'.py')).read_bytes()).hexdigest(),sha)
            option_sources=lambda values:tuple(domain.native_option_collector.OptionSource(
                tuple(v['option_ids']),v['level'],v['condition_value'],v['rank_factor'],v['weight'])for v in values)
            definitions={int(k):v for k,v in common['definitions'].items()}
            for row in common['rows']:
                side=option_sources(row['side_sources']);shared=option_sources(row['shared_sources'])
                record=domain.native_option_collector.collect_side(side,definitions,shared_hp_sources=shared,
                    mode=row['mode'],resonance_level=0,unit_line=0)
                self.assertEqual(record['data'][0],row['shared_hp'])
                if 'context'not in row:continue
                args=dict(row['context'])
                for name in('resonance_points','resonance_definitions','phase_mp_values','unit_mp_values'):
                    args[name]={int(k):v for k,v in args[name].items()}
                args['resonance_definitions']={k:tuple(v)for k,v in args['resonance_definitions'].items()}
                for name in('resonance_override','condition_resistances'):args[name]=tuple(args[name])
                actual=source.assemble(tuple(row['seven']),side,definitions,shared_hp_sources=shared,**args)
                self.assertEqual(struct.pack('<2f',*actual['power']),struct.pack('<2f',*row['native_power']))
                expected=dict(row['native_arguments'])
                for name in('stat_fields','data_fields'):expected[name]={int(k,16):v for k,v in expected[name].items()}
                expected['maps']={int(k,16):{tuple(key)if isinstance(key,list)else key:v for key,v in values}for k,values in expected['maps'].items()}
                self.assertEqual(actual['arguments'],expected)

    def test_current_rank_coefficients_match_original_registration_and_callbacks(self):
        import els_server.domain as domain
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in('native_power_kernel','native_option_scalar_inputs','native_option_scalar_merge',
                'native_option_data_merge','native_option_record_merge','native_option_pre_scale','native_option_metadata',
                'native_ordinary_option_subset','native_option_power_maps','native_option_condition_inputs',
                'native_ordinary_option_power_maps','native_option_factor_inputs','native_extended_option_inputs',
                'native_extended_option_maps','native_option_max_mp','native_option_fixed_hp','native_option_collector','native_rank_coefficient'):
                source=module('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,source,create=True))
            with patch.object(source,'PROJECT_ROOT',ROOT):
                golden=json.loads((REFERENCE/'native-rank-coefficient-source-goldens.json').read_bytes())
                self.assertEqual(len(golden['rows']),30)
                for row in golden['rows']:
                    value=source.coefficient(row['rank']);self.assertEqual(value,row['coefficient'])
                    options=domain.native_option_collector
                    callback=options.OptionSource((golden['option']['ID'],),99,0,value,.3)
                    actual=options.collect_ordinary((callback,),{golden['option']['ID']:golden['option']},
                        mode=row['mode'],resonance_level=200,unit_line=1)
                    self.assertEqual(actual['scalars'],{int(k,16):v for k,v in row['native']['scalars'].items()})
                    self.assertEqual(actual['data'],tuple(row['native']['data']))
                    self.assertEqual(actual['integer_MP'],row['native']['integer_MP'])
                for value in(True,-129,128):
                    with self.assertRaises(ValueError):source.coefficient(value)
            source.catalog.cache_clear()

    def test_original_profile0_rank_source_preserves_missing_updates(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_rank_source_state','els_server/domain/native_rank_coefficient.py')
        golden=json.loads((REFERENCE/'native-fresh-rank-source-goldens-v2.json').read_bytes())
        self.assertEqual(len(golden['rows']),16)
        self.assertEqual(golden['canonical_empty_profile_wire'],'00000000')
        for row in golden['rows']:
            profiles={}if row['profile_rank']is None else{0:row['profile_rank']}
            self.assertEqual(source.rank_after_profile0(profiles,previous_rank=row['previous_rank']),row['native'])
        for profiles,prior in(({0:128},0),({},True),([] ,0)):
            with self.assertRaises(ValueError):source.rank_after_profile0(profiles,previous_rank=prior)

    def test_resistance_option_callback_preserves_its_distinct_rank_scaling(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_metadata':self.option_metadata,
            'els_server.domain.native_extended_option_inputs':self.extended_inputs}):
            source=module('candidate_resistance_option','els_server/domain/native_resistance_option.py')
        golden=json.loads((REFERENCE/'native-resistance-option-goldens-v3.json').read_bytes())
        self.assertEqual(len(golden['rows']),16)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        self.assertEqual({r['alternate_PvE_registry']for r in golden['rows']},{True,False})
        for row in golden['rows']:
            actual=source.merge(tuple(row['before']),row['definition'],**row['args'])
            self.assertEqual(struct.pack('<6f',*actual),struct.pack('<6f',*row['native']))
        with self.assertRaises(ValueError):source.merge((),{},rank_factor=0.,pve_rank_factor=0.,weight=1.)

    def test_resistance_entry_uses_its_original_complementary_phase_predicates(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_metadata':self.option_metadata,
            'els_server.domain.native_extended_option_inputs':self.extended_inputs}):
            source=module('candidate_resistance_entry','els_server/domain/native_resistance_option.py')
        golden=json.loads((REFERENCE/'native-resistance-entry-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),24)
        for row in golden['rows']:
            self.assertEqual(source.eligible(row['definition'],mode=row['mode']),row['native'])

    def test_resistance_skill_sources_match_complete_original_phase(self):
        with patch.dict(sys.modules,{'els_server.domain.native_passive_attributes':self.passives}):
            source=module('candidate_resistance_skills','els_server/domain/native_resistance_skills.py')
        golden=json.loads((REFERENCE/'native-resistance-skills-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),48)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        definitions={int(k):v for k,v in golden['definitions'].items()}
        for row in golden['rows']:
            actual=source.values(definitions,{int(k):v for k,v in row['ranks'].items()},pvp=row['pvp'])
            self.assertEqual(struct.pack('<6f',*actual),struct.pack('<6f',*row['native']))

    def test_armor_resistance_preserves_original_classifier_and_switch(self):
        source=module('candidate_armor_resistance','els_server/domain/native_armor_resistance.py')
        golden=json.loads((REFERENCE/'native-armor-resistance-goldens.json').read_bytes())
        self.assertEqual(golden['executed_cases'],2401)
        self.assertEqual(len(golden['unique_codes']),182)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        for row in golden['unique_codes']:
            self.assertEqual(source.classify(tuple(row['attributes'])),row['code'])
            self.assertEqual(source.values(tuple(row['attributes'])),tuple(row['native']))
        self.assertEqual(source.values((1,1,1,1)),(0.,)*6)
        self.assertEqual(source.values((0,0,4,6)),(0.,0.,0.,0.,110.,0.))
        with self.assertRaises(ValueError):source.values((0,0,0,True))

    def test_four_armor_activation_matches_original_property_and_vector_gates(self):
        source=module('candidate_armor_option_activation','els_server/domain/native_armor_option_activation.py')
        golden=json.loads((REFERENCE/'native-armor-option-activation-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),93)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        for row in golden['rows']:
            selected=[];records={}
            for i,position in enumerate((8,9,10,11)):
                record=bytearray(232);record[0xd5]=position;records[position]=bytes(record)
                selected.append(dict(uid=position,flags4=0,
                    properties=((row['key'],0,0,0,0,0),)if row['mask']&(1<<i)else(),
                    option_vectors={offset:(0,)if row['vector_mask']&(1<<i)else()for offset in(0x248,0x2a8)}))
            self.assertEqual(source.flags(tuple(selected),records)[row['key']],row['native'])

    def test_item_source_factory_matches_whole_native_circuit_wrappers(self):
        import els_server.domain as domain
        names=('native_power_kernel','native_option_scalar_inputs','native_option_scalar_merge','native_option_data_merge',
            'native_option_record_merge','native_option_pre_scale','native_option_metadata','native_ordinary_option_subset',
            'native_option_power_maps','native_option_condition_inputs','native_ordinary_option_power_maps',
            'native_option_factor_inputs','native_extended_option_inputs','native_extended_option_maps','native_option_max_mp',
            'native_option_fixed_hp','native_option_collector','native_dynamic_sets','native_item_option_vectors','native_item_attribute_options',
            'native_circuit_attribute_inputs','native_item_attribute_sources')
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in names:
                source=module('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,source,create=True))
            golden=json.loads((REFERENCE/'native-item-circuit-wrapper-goldens-v2.json').read_bytes())
            circuit=json.loads((REFERENCE/'native-circuit-attribute-inputs-goldens-v3.json').read_bytes())
            known={(r['part'],tuple(r['grid'])):tuple(map(tuple,r['native']))for r in circuit['rows']if'current_template'in r}
            self.assertEqual(len(golden['rows']),8)
            self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
            definitions={int(k):v for k,v in golden['definitions'].items()}
            def restore(value):
                if isinstance(value,dict):return {int(k):restore(v)for k,v in value.items()}
                if isinstance(value,list):return tuple(map(restore,value))
                return value
            def encode(values):return [[list(k)if isinstance(k,tuple)else k,v]for k,v in sorted(values.items())]
            for row in golden['rows']:
                projected={};callbacks=[];activation={int(k):v for k,v in row['activation'].items()}
                for item in row['items']:
                    record=bytes.fromhex(item['record_hex']);v=dict(item['row']);part=record[0xd5]
                    v['properties']=restore(v['properties']);v['template_options']=tuple(v['template_options']);v['option_vectors']=restore(v['option_vectors'])
                    projected[v['template_id']]=part
                    with patch.object(source,'circuit_options',lambda identity,grid:known[projected[identity],tuple(grid)]):
                        callbacks.extend(source.callbacks(v,record,character_level=99,category77=False,
                            activation=activation,circuit_state=0,rank_factor=0.))
                callbacks=tuple(callbacks)
                self.assertEqual([dict(option_ids=list(s.option_ids),level=s.level,condition_value=s.condition_value,
                    rank_factor=s.rank_factor,weight=s.weight)for s in callbacks],row['sources'])
                initial=dict(row['initial']);initial['resistances']=tuple(initial['resistances'])
                for key in('damage','alternate'):initial[key]={k:v for k,v in initial[key]}
                actual=domain.native_option_collector.collect_ordinary(callbacks,definitions,**row['args'])
                actual|=domain.native_option_collector.collect_extended(callbacks,definitions,initial,**row['args'])
                native=row['native']
                self.assertEqual(actual['scalars'],{int(k,16):v for k,v in native['scalars'].items()})
                self.assertEqual(struct.pack('<13f',*actual['data']),struct.pack('<13f',*native['data']))
                self.assertEqual(actual['integer_MP'],native['integer_MP'])
                for key in('capabilities','probability','damage','alternate','extended_capabilities'):
                    self.assertEqual(encode(actual[key]),native[key])
                self.assertEqual(list(actual['resistances']),native['resistances'])

    def test_circuit_weights_match_complete_original_source_and_current_branches(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_circuit_attribute_inputs','els_server/domain/native_circuit_attribute_inputs.py')
        golden=json.loads((REFERENCE/'native-circuit-attribute-inputs-goldens-v3.json').read_bytes())
        self.assertEqual(len(golden['rows']),36)
        self.assertEqual(sum('current_template'in row for row in golden['rows']),8)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        definitions={int(k):v for k,v in golden['definitions'].items()}
        ports={int(k):tuple(v)for k,v in golden['ports'].items()}
        for row in golden['rows']:
            actual=source.weighted_options(tuple(row['active_slots']),tuple(row['grid']),definitions,ports)
            self.assertEqual(actual,tuple(map(tuple,row['native'])))
        with self.assertRaises(ValueError):source.weighted_options((0,0),(0,)*16,definitions,ports)

    def test_complete_current_character_wire_context_and_clear_boundary(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            rank=module('candidate_character_rank_context','els_server/domain/native_rank_coefficient.py')
        with patch.dict(sys.modules,{'els_server.domain.native_rank_coefficient':rank}):
            source=module('candidate_character_copy_context','els_server/domain/native_character_context.py')
        golden=json.loads((REFERENCE/'native-pve-wire-source-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),5)
        clear=json.loads((REFERENCE/'native-character-named-clear-goldens.json').read_bytes())
        self.assertEqual(len(clear['rows']),5)
        for row in golden['rows']:
            for previous in(0,7,-128,127):
                current=source.after_character_copy(bytes(4),bytes.fromhex(row['wire_hex']),previous_rank=previous)
                self.assertEqual(current.rank,previous)
                self.assertEqual(current.pve(),row['native'])
                self.assertEqual(current.world_buff_ids,())
        for profile,pve in((b'',bytes(25)),(b'\0\0\0\1',bytes(25)),(bytes(4),bytes(24))):
            with self.assertRaises(ValueError):source.after_character_copy(profile,pve,previous_rank=0)

    def test_resistance_service_lifecycle_and_finalization_match_original(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_resistance_finalization','els_server/domain/native_resistance_finalization.py')
        golden=json.loads((REFERENCE/'native-resistance-finalization-goldens.json').read_bytes())
        self.assertEqual(len(golden['service_rows']),7)
        self.assertEqual(len(golden['finalization_rows']),6)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        for row in golden['service_rows']:
            previous=None if row['previous']is None else tuple(row['previous'])
            expected=None if row['native']is None else tuple(row['native'])
            self.assertEqual(source.service_after_311(previous,row['threshold']),expected)
        for row in golden['finalization_rows']:
            args=dict(row['args'])
            for key in('skill_values','service_values'):
                if args[key]is not None:args[key]=tuple(args[key])
            args['post_values']=tuple(map(tuple,args['post_values']))
            self.assertEqual(struct.pack('<6f',*source.finish(tuple(row['before']),**args)),struct.pack('<6f',*row['native']))
        with self.assertRaises(ValueError):source.service_after_311(None,65536)

    def test_legacy_socket_first_match_and_signed_threshold_match_original(self):
        source=module('candidate_legacy_socket_condition','els_server/domain/native_legacy_socket_condition.py')
        golden=json.loads((REFERENCE/'native-legacy-socket-requirement-goldens.json').read_bytes())
        definitions={int(k):v for k,v in golden['definitions'].items()}
        self.assertEqual(len(golden['rows']),73)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        for row in golden['rows']:
            options=tuple(row['options']);expected=(row['count'],row['minimum'])if row['count']>0 else None
            self.assertEqual(source.requirement(options,definitions),expected)
            for count,native in zip((0,1,2,3,7),row['decisions']):
                self.assertEqual(source.enabled(options,definitions,piece_count=count),native)
        self.assertEqual(golden['current_gate_definitions'],24744)
        self.assertEqual(sum(v['count']for v in golden['current_gate_profiles']),24744)
        self.assertTrue(all(row['native'][1]==0 for row in golden['current_gate_profiles']))
        with self.assertRaises(ValueError):source.enabled((),definitions,piece_count=-1)

    def test_resistance_circuit_weights_and_legacy_activation_match_native_item_phase(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_extended_option_inputs':self.extended_inputs,
            'els_server.domain.native_option_metadata':self.option_metadata}):
            source=module('candidate_resistance_weighted_item_order','els_server/domain/native_resistance_item_options.py')
            option=module('candidate_resistance_weighted_option_entry','els_server/domain/native_resistance_option.py')
        gate=module('candidate_resistance_legacy_gate','els_server/domain/native_legacy_socket_condition.py')
        golden=json.loads((REFERENCE/'native-resistance-circuit-legacy-goldens-v2.json').read_bytes())
        self.assertEqual(len(golden['rows']),64)
        definitions={int(k):v for k,v in golden['definitions'].items()}
        def restore(value):
            if isinstance(value,dict):return {int(k):restore(v)for k,v in value.items()}
            if isinstance(value,list):return tuple(map(restore,value))
            return value
        for row in golden['rows']:
            args=dict(row['args']);args['circuit_options']=tuple(map(tuple,args['circuit_options']))
            args['allow4']=gate.enabled(tuple(row['template_options']),definitions,piece_count=row['piece_count'])
            actual=source.collect(restore(row['vectors']),tuple(map(tuple,row['properties'])),tuple(row['template_options']),**args)
            filtered=tuple(pair for pair in actual if pair[0]in definitions and option.eligible(definitions[pair[0]],mode=row['mode']))
            self.assertEqual(filtered,tuple(map(tuple,row['native'])))

    def test_resistance_item_sources_preserve_distinct_main_and_secondary_order(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_resistance_item_order','els_server/domain/native_resistance_item_options.py')
        vectors=module('candidate_resistance_item_vectors','els_server/domain/native_item_option_vectors.py')
        golden=json.loads((REFERENCE/'native-resistance-item-phase-goldens.json').read_bytes())
        self.assertEqual(len(golden['rows']),136)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        for row in golden['rows']:
            groups=tuple(tuple(v)for v in row['groups'])
            args=dict(row['args']);args['circuit_options']=tuple(map(tuple,args['circuit_options']))
            actual=source.collect(vectors.project(groups,{},mutations=()),tuple(map(tuple,row['properties'])),
                tuple(row['template_options']),**args)
            self.assertEqual(tuple(pair for pair in actual if pair[0]),tuple(map(tuple,row['native'])))

    def test_pve_rank_registries_and_resistance_context_match_original(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power,
            'els_server.domain.native_option_scalar_inputs':self.option_scalars,
            'els_server.domain.native_option_metadata':self.option_metadata,
            'els_server.domain.native_extended_option_inputs':self.extended_inputs}):
            source=module('candidate_pve_rank_source','els_server/domain/native_pve_rank_coefficient.py')
            resistance=module('candidate_pve_rank_resistance','els_server/domain/native_resistance_option.py')
        with patch.object(source,'PROJECT_ROOT',ROOT), patch.dict(sys.modules,{
            'els_server.domain.native_option_scalar_inputs':self.option_scalars}):
            golden=json.loads((REFERENCE/'native-pve-rank-source-goldens.json').read_bytes())
            self.assertEqual(len(golden['rows']),24)
            for row in golden['rows']:
                self.assertEqual(source.coefficient(row['rank'],for_mp=row['for_mp']),row['native'])
            for rank in(-128,-1,10,127):
                with self.assertRaises(ValueError):source.coefficient(rank,for_mp=True)
            golden=json.loads((REFERENCE/'native-pve-rank-resistance-goldens.json').read_bytes())
            self.assertEqual(len(golden['rows']),34)
            self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
            for row in golden['rows']:
                coefficient=source.factor(row['definition'],**row['context'])
                self.assertEqual(coefficient,row['coefficient'])
                actual=resistance.merge(tuple(row['before']),row['definition'],rank_factor=0.,
                    pve_rank_factor=coefficient,weight=row['weight'])
                self.assertEqual(struct.pack('<6f',*actual),struct.pack('<6f',*row['native']))
        source.catalog.cache_clear()

    def test_worn_category77_source_uses_existing_pinned_original_registry(self):
        import els_server.domain as domain
        import els_server.paths as paths
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in('native_dynamic_sets','native_item_option_vectors','native_option_colors','native_set_sources','native_worn_source_inputs'):
                source=module('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,source,create=True))
            rows=json.loads((REFERENCE/'native-division77-source-goldens.json').read_bytes())['rows']
            source.category77_registry.cache_clear()
            with patch.object(paths,'PROJECT_ROOT',ROOT):
                actual=source.category77_membership(tuple(r['template']for r in rows if r['template']>0))
            self.assertEqual(actual,{r['template']:r['native']for r in rows if r['template']>0})
            self.assertEqual(sum(actual.values()),135)
            source.category77_registry.cache_clear()


    def test_resistance_service_and_post_composition_matches_whole_native(self):
        import els_server.domain as domain
        names=('native_power_kernel','native_option_scalar_inputs','native_extended_option_inputs',
            'native_option_metadata','native_resistance_option','native_pve_rank_coefficient',
            'native_rank_coefficient','native_resistance_finalization','native_legacy_socket_condition',
            'native_resistance_item_options','native_circuit_attribute_inputs','native_armor_resistance',
            'native_passive_attributes','native_resistance_skills','native_resistance_composition')
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in names:
                source=module('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,source,create=True))
                if hasattr(source,'PROJECT_ROOT'):source.PROJECT_ROOT=ROOT
            golden=json.loads((REFERENCE/'native-resistance-composed-tail-goldens.json').read_bytes())
            self.assertEqual(len(golden['rows']),8)
            self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
            definitions={int(k):v for k,v in golden['definitions'].items()}
            for row in golden['rows']:
                args=dict(row['args'])
                for key in('skill_values','service_values','post_option_ids'):
                    if args[key]is not None:args[key]=tuple(args[key])
                actual=source.finish(tuple(row['before']),definitions,**args)
                self.assertEqual(struct.pack('<6f',*actual['values']),struct.pack('<6f',*row['native']))
                self.assertEqual(actual['callbacks'],tuple(tuple(v)for v in row['post_callbacks']))

    def test_current_force_stat_rank_sources_follow_native_visible_slots(self):
        source=module('candidate_native_force_stat_sources','els_server/domain/native_skill_query_sources.py')
        golden=json.loads((REFERENCE/'native-force-stat-rank-source-goldens-v3.json').read_bytes())
        self.assertEqual(len(golden['rows']),56)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        kinds={int(k):v for k,v in golden['skill_types'].items()}
        for row in golden['rows']:
            visible=tuple(tuple(pair)for pair in row['visible_slots'])
            actual=source.passive_ranks(visible,kinds)
            native={sid:rank for sid,rank in row['native']if rank}
            self.assertEqual(actual,native)
        empty=((0,0),)*11
        for pair in((2**31,1),(1,256),(1,0),(-1,1)):
            with self.assertRaises(ValueError):source.passive_ranks((pair,)+empty[1:],{1:17})
        with self.assertRaises(ValueError):source.passive_ranks(((1,1),(1,1))+empty[2:],{1:17})
        with self.assertRaises(ValueError):source.passive_ranks(((1,1),)+empty[1:],{1:18})

    def test_fixed_HP_source_matches_whole_native_callback_and_pipeline(self):
        import els_server.domain as domain
        names=('native_power_kernel','native_option_scalar_inputs','native_option_scalar_merge',
            'native_option_data_merge','native_option_record_merge','native_option_pre_scale',
            'native_option_metadata','native_ordinary_option_subset','native_option_power_maps',
            'native_option_condition_inputs','native_ordinary_option_power_maps','native_option_factor_inputs',
            'native_extended_option_inputs','native_extended_option_maps','native_option_max_mp',
            'native_option_fixed_hp','native_option_collector')
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules))
            for name in names:
                current=module('els_server.domain.'+name,'els_server/domain/'+name+'.py')
                stack.enter_context(patch.object(domain,name,current,create=True))
            fixed=domain.native_option_fixed_hp;collector=domain.native_option_collector
            golden=json.loads((REFERENCE/'native-fixed-hp-goldens.json').read_bytes())
            self.assertEqual(golden['cases'],432)
            self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(fixed.__file__).read_bytes()).hexdigest())
            for row in golden['rows']:
                actual=fixed.merge(row['before'],row['definition'],**row['args'])
                self.assertEqual(struct.pack('<f',actual),struct.pack('<f',row['native']))
                if row['before']==0.:
                    args=row['args'];d=row['definition']
                    source=collector.OptionSource((d['ID'],),args['level'],0,args['rank_factor'],args['weight'])
                    result=collector.collect_ordinary((source,),{d['ID']:d},
                        mode=args['mode'],resonance_level=args['resonance_level'],unit_line=args['unit_line'])
                    self.assertEqual(struct.pack('<f',result['fixed_HP']),struct.pack('<f',row['native']))

    def test_native_side_pair_keeps_selectors_separate_from_phase_mode(self):
        with patch.dict(sys.modules,{'els_server.domain.native_power_kernel':self.power}):
            source=module('candidate_native_attribute_sides','els_server/domain/native_attribute_sides.py')
        golden=json.loads((REFERENCE/'native-luciel-side-pair-goldens-v2.json').read_bytes())
        self.assertEqual(golden['classes'],13)
        self.assertEqual(golden['source_sha256'],hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest())
        expected=dict(owner_uid=1,unit_type=10,unit_class=200,generation=7,source_sha256='0'*64,pvp_mode=0,at=1793000000)
        for row in golden['rows']:
            args=dict(expected,unit_class=row['class_id'])
            sides=tuple(source.CalculatedSide(1,10,row['class_id'],7,'0'*64,v['selector'],v['pvp_mode'],tuple(v['seven']),tuple(v['power']),None)for v in row['sides'])
            actual=source.notification_sides(*sides,**args)
            self.assertEqual(actual['first_seven'],sides[0].seven)
            self.assertEqual(actual['second_seven'],sides[1].seven)
            self.assertNotEqual(actual['first_seven'],actual['second_seven'])
            self.assertEqual(struct.pack('<f',actual['power']),struct.pack('<f',row['native_cache_power']))
        first,second=sides;expected['unit_class']=first.unit_class
        for field,value in(('owner_uid',2),('owner_uid',True),('unit_type',5),('unit_class',1),
            ('generation',8),('source_sha256','1'*64),('pvp_mode',1),('selector',0),('valid_before',1793000000)):
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                source.notification_sides(first,replace(second,**{field:value}),**expected)
        with self.assertRaises(ValueError):source.notification_sides(first,None,**expected)
        normal=replace(first,unit_type=5,unit_class=164)
        args=dict(expected,unit_type=5,unit_class=164)
        self.assertEqual(source.notification_sides(normal,None,**args)['second_seven'],normal.seven)
        with self.assertRaises(ValueError):source.notification_sides(normal,second,**args)
        for row in golden['max_controls']:
            a=replace(first,power=(row['first'],0.));b=replace(second,power=(row['second'],0.))
            actual=source.notification_sides(a,b,**expected)['power']
            self.assertEqual(struct.pack('<f',actual).hex(),row['native_bits'])


if __name__=='__main__':unittest.main()
