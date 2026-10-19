import copy
import unittest
from unittest.mock import patch

from els_server.domain.manufacture_requirements import requirements, inventory_candidates
from els_server.protocol.profession_messages import ProfessionState


class ManufactureRequirementsTests(unittest.TestCase):
    def test_output_policy_rejects_entire_pool_and_keeps_history(self):
        import struct
        from els_server.domain.manufacture_requirements import require_output_references
        from els_server.domain.manufacture_requirements import inspect_request
        from els_server.domain.acquisition_policy import excluded_equipment
        from els_server.manufacture_data import manufacture_data
        old=next(iter(excluded_equipment()))
        for candidates in ([],[2147483647],[old],[77000,old],[True]):
            with patch('els_server.domain.manufacture_requirements.manufacture_data') as catalog:
                catalog.return_value.recipe.return_value={'result_registrations':candidates}
                before=copy.deepcopy(candidates)
                with self.assertRaises(ValueError):require_output_references(1)
                self.assertEqual(candidates,before)
        candidates=[77000,77420,77000]
        with patch('els_server.domain.manufacture_requirements.manufacture_data') as catalog:
            catalog.return_value.recipe.return_value={'result_registrations':candidates}
            self.assertEqual(require_output_references(1),tuple(candidates))
        catalog=manufacture_data()
        identity=next(i for i in catalog.ids()
                      if set(catalog.recipe(i)['result_registrations']) & excluded_equipment())
        before=catalog.recipe(identity)
        with self.assertRaises(ValueError):require_output_references(identity)
        self.assertEqual(catalog.recipe(identity),before)
        items=[dict(uid=101,template=77000,metadata=2,count=7,group=6,slot=0)]
        before_items=copy.deepcopy(items)
        with self.assertRaises(ValueError):
            inspect_request(struct.pack('>iiqI',identity,1,-1,0),items,now=2000000000,
                            profession_state=ProfessionState(profession=3,level=255))
        self.assertEqual(items,before_items)

    def test_profession_native_comparison_and_all_catalog_requirements(self):
        import json
        from pathlib import Path
        from els_server.domain.manufacture_requirements import inspect_profession
        from els_server.protocol.profession_messages import ProfessionState
        from els_server.manufacture_data import manufacture_data
        proof=json.loads((Path(__file__).resolve().parents[1] /
            'analysis/integration-20261015/manufacture-profession-native.json').read_text())
        for case in proof['cases']:
            definition=dict(m_RequireProfessionType=case['required'],m_LimitProfessionLevel=case['minimum'])
            with patch('els_server.domain.manufacture_requirements.manufacture_data') as catalog:
                catalog.return_value.recipe.return_value={'definition':definition}
                state=ProfessionState(profession=case['profession'],level=case['level'])
                if bool(case['required']) != bool(case['minimum']):
                    with self.assertRaises(ValueError):inspect_profession(1,state)
                else:
                    result=inspect_profession(1,state)
                    self.assertEqual(result['has_requirement'],case['has_requirement'])
                    self.assertEqual(result['satisfied'],case['satisfied'])
        catalog=manufacture_data(); restricted=0
        for identity in catalog.ids():
            definition=catalog.recipe(identity)['definition']
            minimum=definition.get('m_LimitProfessionLevel',0)
            required=definition.get('m_RequireProfessionType',0)
            self.assertTrue(inspect_profession(identity,ProfessionState(profession=required,level=minimum))['fits'])
            if required:
                restricted+=1
                self.assertFalse(inspect_profession(identity,ProfessionState(profession=required,level=minimum-1))['fits'])
                self.assertFalse(inspect_profession(identity,ProfessionState(profession=0,level=255))['fits'])
        self.assertEqual(restricted,34)
        with self.assertRaises(ValueError):inspect_profession(30445,None)
        with self.assertRaises(ValueError):inspect_profession(0,ProfessionState())

    def test_native_quota_boundaries_and_invalid_state(self):
        import json
        from pathlib import Path
        from els_server.domain.manufacture_requirements import inspect_limit
        proof = json.loads((Path(__file__).resolve().parents[1] /
            'analysis/integration-20261015/manufacture-limit-native.json').read_text())
        for case in proof['cases']:
            result = inspect_limit(**{k:case[k] for k in ('maximum','used','quantity')})
            self.assertEqual(result['fits'], case['accepted'])
            self.assertFalse(result['transaction_implemented'])
        for key in ('maximum','used','quantity'):
            for invalid in (None, True, -1, 1.5, 2**31):
                args = dict(maximum=30,used=0,quantity=1)
                args[key] = invalid
                with self.subTest(key=key,invalid=invalid),self.assertRaises(ValueError):
                    inspect_limit(**args)
        self.assertFalse(inspect_limit(maximum=2**31-1,used=2**31-1,quantity=1)['fits'])

    def test_auxiliary_uid_modes_never_remove_material_costs(self):
        recipe={'m_Cost':0,'m_MaterialTable':{
            '1':{'m_MaterialID':77000,'m_MaterialCount':3},
            '2':{'m_MaterialID':60100,'m_MaterialCount':1},
            '3':{'m_MaterialID':2147483647,'m_MaterialCount':2}}}
        with patch('els_server.domain.manufacture_requirements.manufacture_data') as catalog:
            catalog.return_value.recipe.return_value={'definition':recipe,'result_registrations':[77000]}
            result=requirements(1,2)
        self.assertEqual(result['auxiliary_uid_modes'],{77000:'omitted_by_client',
            60100:'instance_candidate',2147483647:'unknown_definition'})
        self.assertEqual(result['materials'],{77000:6,60100:2,2147483647:4})

    def test_native_recipe_batch_and_overflow_rejection(self):
        result = requirements(30445,7)
        self.assertEqual(result['base_ed'],1881600)
        self.assertEqual(result['materials'],{154059:7,154053:4200})
        self.assertFalse(result['transaction_implemented'])
        # This positive wire quantity is accepted by the native client's
        # overflow-prone material predicate, but must fail server preflight.
        with self.assertRaisesRegex(ValueError,'overflow'):requirements(30445,2**31-1)
        for n in (0,-1,True,1.0,2**31):
            with self.subTest(n=n),self.assertRaises(ValueError):requirements(30445,n)

    def test_repeated_material_rows_cannot_double_count_inventory(self):
        recipe = {'m_Cost':3,'m_MaterialTable':{
            '1':{'m_MaterialID':77000,'m_MaterialCount':5},
            '2':{'m_MaterialID':77000,'m_MaterialCount':7}}}
        with patch('els_server.domain.manufacture_requirements.manufacture_data') as catalog:
            catalog.return_value.recipe.return_value={'definition':recipe,'result_registrations':[77000]}
            self.assertEqual(requirements(1,2)['materials'],{77000:24})
            recipe['m_MaterialTable']['1']['m_MaterialCount']=2**30
            recipe['m_MaterialTable']['2']['m_MaterialCount']=2**30
            with self.assertRaisesRegex(ValueError,'overflow'):requirements(1)
            recipe['m_MaterialTable']['1']['m_MaterialID']=100002375
            with self.assertRaisesRegex(ValueError,'Unsupported'):requirements(1)

    def test_native_lock_boundary_distinct_from_expiration_and_no_mutation(self):
        now=2000000000
        base=dict(uid=101,template=77000,metadata=2,count=7,group=6,slot=0)
        items=[base,{**base,'uid':102,'slot':1,'lock_until':now},
               {**base,'uid':103,'slot':2,'lock_until':now-1},
               {**base,'uid':104,'slot':3,'expires_at':now},
               {**base,'uid':105,'slot':4,'expires_at':now-1}]
        before=copy.deepcopy(items)
        self.assertEqual(inventory_candidates(items,now=now),{77000:((101,7),(103,7),(104,7))})
        self.assertEqual(items,before)
        with self.assertRaises(ValueError):inventory_candidates(items,now=True)

    def test_native_count_differential(self):
        # Same real encoded inputs as the original native material replay.
        import json
        from els_server.paths import PROJECT_ROOT
        proof=json.loads((PROJECT_ROOT/'analysis/integration-20261015/manufacture-material-native.json').read_text())
        native=next(c for c in proof['cases'] if c['case']=='real-wire-multiple-UIDs')
        base=dict(uid=0x100000001,template=77000,metadata=2,count=7,group=6,slot=0)
        items=[base,{**base,'uid':base['uid']+1,'slot':1,'count':3},
               {**base,'uid':base['uid']+2,'slot':2,'count':5,'lock_until':2000000000}]
        candidates=inventory_candidates(items,now=2000000000)
        self.assertEqual(sum(n for _,n in candidates[77000]),native['usable'])

    def test_equipped_items_and_duplicate_identity_rejected(self):
        from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS,VERIFIED_TEMPLATES
        template=81021
        equipped=dict(uid=1,template=template,metadata=VERIFIED_TEMPLATES[template],count=1,
                      group=9,slot=FASHION_EQUIP_SLOTS[template])
        self.assertEqual(inventory_candidates([equipped],now=2000000000),{})
        for duplicate in (equipped,{**equipped,'uid':2}):
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                inventory_candidates([equipped,duplicate],now=2000000000)

    def test_explicit_uid_is_not_replaced_by_other_available_stack(self):
        import struct
        from els_server.domain.manufacture_requirements import inspect_request
        base=dict(uid=101,template=77000,metadata=2,count=7,group=6,slot=0)
        items=[base,{**base,'uid':102,'slot':1,'lock_until':2000000000},
               {**base,'uid':103,'slot':2,'template':77420}]
        recipe={'m_Cost':3,'m_MaterialTable':{'1':{'m_MaterialID':77000,'m_MaterialCount':5}}}
        with patch('els_server.domain.manufacture_requirements.manufacture_data') as catalog:
            catalog.return_value.recipe.return_value={'definition':recipe,'result_registrations':[77000]}
            for selected in (102,103,999):
                with self.subTest(selected=selected),self.assertRaises(ValueError):
                    inspect_request(struct.pack('>iiqI',1,1,selected,0),items,now=2000000000,
                                    profession_state=ProfessionState())
            result=inspect_request(struct.pack('>iiqI',1,2,101,0),items,now=2000000000,
                                   profession_state=ProfessionState())
            self.assertEqual(result['selected_uid'],101)
            self.assertEqual(result['shortages'],{77000:3})
            self.assertFalse(result['transaction_implemented'])
            with self.assertRaises(ValueError):
                inspect_request(struct.pack('>iiqIq',1,1,-1,1,102),items,now=2000000000,
                                profession_state=ProfessionState())

    def test_request_enforces_profession_before_inventory_preflight(self):
        import struct
        from els_server.domain.manufacture_requirements import inspect_request
        payload=struct.pack('>iiqI',10078906,1,-1,0)
        for state in (ProfessionState(),ProfessionState(profession=2,level=255),
                      ProfessionState(profession=3,level=7)):
            with self.subTest(state=state),self.assertRaisesRegex(ValueError,'profession requirement'):
                inspect_request(payload,[],now=2000000000,profession_state=state)
        with self.assertRaises(ValueError):
            inspect_request(payload,[],now=2000000000,profession_state=None)
        result=inspect_request(payload,[],now=2000000000,
                               profession_state=ProfessionState(profession=3,level=8))
        self.assertTrue(result['profession']['satisfied'])
        self.assertTrue(result['shortages'])
        self.assertFalse(result['transaction_implemented'])


if __name__=='__main__':unittest.main()
