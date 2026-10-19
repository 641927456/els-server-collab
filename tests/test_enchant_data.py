import hashlib,json,tempfile,unittest
from pathlib import Path
from els_server.enchant_data import EnchantData,enchant_data
from els_server.game_data import DATA_DIR,client_data
from tools.build_enchant_catalog import build,ROOT
from els_server.domain.enchant_rules import attribute_count,normal_item_quote,attribute_quote

class EnchantDataTests(unittest.TestCase):
    def test_material_rule_against_all_native_queries_and_missing_rows(self):
        witness=json.loads((ROOT/'analysis/integration-20261015/enchant-rules-native.json').read_text())
        self.assertEqual(len(witness['rows']),7140);self.assertEqual(witness['special_templates'],[])
        self.assertFalse(witness['applied_to_game']);catalog=enchant_data()
        for row in witness['rows']:
            args=(bool(row['weapon']),row['count'],row['level'],row['grade'])
            if row['ok']:
                self.assertEqual(catalog.normal_material_cost(*args)['quantity'],row['quantity'])
            else:
                with self.assertRaises(ValueError):catalog.normal_material_cost(*args)
        for args in ((1,0,1,1),(True,False,1,1),(True,0,False,1),(True,0,1,True)):
            with self.assertRaises(ValueError):catalog.normal_material_cost(*args)

    def test_exhaustive_native_element_compatibility(self):
        witness=json.loads((ROOT/'analysis/integration-20261015/enchant-rules-native.json').read_text())
        self.assertEqual(len(witness['compatibility']),16807)
        for row in witness['compatibility']:
            self.assertEqual(enchant_data().elements_compatible(row['slots'],row['target']),bool(row['allowed']))
        for slots,target in (([1,2,3],1),([7,0,0,0],1),([False,0,0,0],1),([0]*4,0),([0]*4,8),([0]*4,True)):
            with self.assertRaises(ValueError):enchant_data().elements_compatible(slots,target)

    def test_quote_uses_template_capacity_and_stays_non_transactional(self):
        data=client_data();samples={}
        with data.connect() as db:
            ids=[row[0] for row in db.execute('SELECT id FROM items WHERE item_type IN (1,2)')]
        for identity in ids:
            row=data.item(identity);level=row['record'][0xd9] or row['record'][0xd1]
            if 1<=level<=100 and 0<row['record'][0xd8]<=4 and 1<=row['flags4']>>20&15<=6:
                samples.setdefault(row['item_type'],identity)
            if len(samples)==2:break
        self.assertEqual(len(samples),2)
        for template in samples.values():
            quote=attribute_quote(template,[0]*4,1)
            self.assertTrue(quote['can_add_by_slot_rules']);self.assertEqual(quote['material']['template'],0x1fc00)
            self.assertGreater(quote['material']['quantity'],0)
            self.assertFalse(quote['eligibility_verified']);self.assertFalse(quote['authorizes_transaction'])
            self.assertFalse(attribute_quote(template,[1,0,0,0],2)['can_add_by_slot_rules'])
            full=attribute_quote(template,[1]*4,1)
            self.assertFalse(full['can_add_by_slot_rules']);self.assertIsNone(full['material'])
        for target in range(1,8):self.assertEqual(data.item(data.enchanting.material_template(target))['id'],data.enchanting.material_template(target))

    def test_price_against_native_vm_not_python_generated_values(self):
        witness=json.loads((ROOT/'analysis/integration-20261015/enchant-cost-native.json').read_text())
        self.assertEqual(witness['count'],420);self.assertTrue(witness['stack_unchanged'])
        for row in witness['rows']:
            count,weapon,level,grade=row['args']
            self.assertEqual(enchant_data().normal_ed_cost(count,bool(weapon),level,grade),row['cost'])
        for args in ((-1,True,1,1),(5,True,1,1),(0,1,1,1),(0,True,-1,1),(0,True,256,1),(0,True,1,7),(False,True,1,1)):
            with self.assertRaises(ValueError):enchant_data().normal_ed_cost(*args)

    def test_native_material_maps_and_inventory_slot_counter(self):
        witness=json.loads((ROOT/'analysis/integration-20261015/enchant-material-native.json').read_text())
        self.assertTrue(witness['consistent_double_read']);self.assertEqual(len(witness['rows']),700)
        grades={1:'UNIQUE',2:'ELITE',3:'RARE',4:'NORMAL',5:'LOW',6:'LEGEND'}
        for row in witness['rows']:
            for grade,quantity in row['grades'].items():
                self.assertEqual(enchant_data().material_quantity(row['enchant_type'],row['source_index'],grades[int(grade)]),quantity)
        self.assertEqual(len(witness['private_count_cases']),81)
        for row in witness['private_count_cases']:self.assertEqual(attribute_count(row['slots']),row['count'])
        for slots in ([],[0]*5,[False,0,0,0],[2**31,0,0,0]):
            with self.assertRaises(ValueError):attribute_count(slots)

    def test_item_price_arguments_follow_native_record(self):
        with client_data().connect() as db:
            ids=[row[0] for row in db.execute('SELECT id FROM items WHERE item_type IN (1,2) LIMIT 20')]
        for template in ids:
            row=client_data().item(template);quote=normal_item_quote(template,[1001,0,-1,0])
            self.assertEqual(quote['existing_count'],1)
            self.assertEqual(quote['equipment_level'],row['record'][0xd9] or row['record'][0xd1])
            self.assertFalse(quote['authorizes_transaction']);self.assertFalse(quote['eligibility_verified'])
        with self.assertRaises(ValueError):normal_item_quote(77000,[0]*4)

    def test_native_resource_rebuild_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)
            build(ROOT/'analysis/integration-20261015/enchant-native',destination)
            self.assertEqual((destination/'enchanting.json').read_bytes(),(DATA_DIR/'enchanting.json').read_bytes())
            self.assertEqual(EnchantData(destination).manifest['counts'],enchant_data().manifest['counts'])

    def test_full_material_matrix_and_no_silent_fallback(self):
        d=enchant_data()
        for t in range(1,8):
            for index in range(1,101):
                for grade in ('LOW','NORMAL','RARE','ELITE','UNIQUE','LEGEND'):
                    self.assertGreater(d.material_quantity(t,index,grade),0)
        self.assertEqual(d.material_quantity(1,1,'LEGEND'),2)
        self.assertEqual(d.material_quantity(7,100,'LOW'),78)
        for args in ((0,1,'LOW'),(8,1,'LOW'),(1,0,'LOW'),(1,101,'LOW'),(1,1,'INVALID'),(True,1,'LOW')):
            with self.assertRaises(ValueError):d.material_quantity(*args)

    def test_variants_missing_ids_and_immutable_results(self):
        d=enchant_data();player=d.effect(1001);npc=d.effect(1001,npc=True)
        self.assertEqual(client_data().enchanting.effect(1001),player)
        self.assertNotIn('bIsForNPC',player);self.assertTrue(npc['bIsForNPC'])
        player['m_fRate']=100
        self.assertEqual(d.effect(1001)['m_fRate'],.05)
        self.assertTrue(d.scroll(130147)['item_present'])
        old=d.scroll(154004);self.assertFalse(old['item_present']);self.assertFalse(old['activation_implemented'])
        with self.assertRaises(ValueError):d.effect(None)
        with self.assertRaises(ValueError):d.effect(999999)
        with self.assertRaises(ValueError):d.scroll(0)

    def test_checksum_and_duplicate_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);raw=(DATA_DIR/'enchanting.json').read_bytes();m=json.loads((DATA_DIR/'enchanting.manifest.json').read_text())
            (p/'enchanting.json').write_bytes(raw+b' ');(p/'enchanting.manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):EnchantData(p)
            data=json.loads(raw);data['requirements'][1]=data['requirements'][0]
            raw=json.dumps(data).encode();m['sha256']=hashlib.sha256(raw).hexdigest()
            (p/'enchanting.json').write_bytes(raw);(p/'enchanting.manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):EnchantData(p)
