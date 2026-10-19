import copy,json,sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data
from els_server.domain.normal_equipment import definitions,validate_proof
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS,VERIFIED_TEMPLATES,validate_item
from els_server.domain.local_session import LocalAccount
from els_server.domain.enchant_rules import attribute_quote
from els_server.storage.local_state import LocalState
from tests.historical_inventory import seed_existing_items as grant_items
from els_server.storage.attribute_enchant import change_attribute,SUPPORTED_EQUIPMENT


class NormalEquipmentTests(unittest.TestCase):
    def test_full_native_coverage_and_no_implicit_wear(self):
        from tools.audit_enchant_equipment import audit
        coverage=audit();catalog=definitions()
        self.assertEqual(len(catalog),40604)
        self.assertEqual(set(catalog),set(coverage['normal_rule_candidates']))
        self.assertEqual(SUPPORTED_EQUIPMENT,set(catalog))
        self.assertFalse(set(catalog)&set(FASHION_EQUIP_SLOTS))
        self.assertTrue(all(VERIFIED_TEMPLATES[t]==1 for t in catalog))
        self.assertNotIn(69865,catalog)
        with self.assertRaises(TypeError):catalog[130]['group']=9
        with self.assertRaises(ValueError):validate_item(dict(uid=1,template=130,metadata=1,count=1,group=9,slot=0))

    def test_evidence_rejects_tampering(self):
        manifest=json.loads((PROJECT_ROOT/'els_server/data/normal_equipment.manifest.json').read_text())
        proof=json.loads((PROJECT_ROOT/manifest['proof']).read_text());row=proof['rows'][0];template=row['template']
        proof=dict(proof,count=1,accepted_count=1,rows=[row]);manifest=dict(manifest,count=1)
        records={template:client_data().item(template)['record']}
        self.assertEqual(set(validate_proof(manifest,proof,records)),{template})
        for field,value in [('restriction',1),('size',304),('slots',[6]*4),('level_value',-1)]:
            bad=copy.deepcopy(proof);bad['rows'][0]['cases'][1][field]=value
            with self.assertRaises(ValueError):validate_proof(manifest,bad,records)
        bad=copy.deepcopy(proof);bad['rows'][0]['source']['flags4']^=1
        with self.assertRaises(ValueError):validate_proof(manifest,bad,records)
        with self.assertRaises(ValueError):validate_proof(manifest,proof,{template:bytes(232)})

    def test_every_kind_grade_capacity_bucket_transaction_and_reload(self):
        from tools.audit_enchant_equipment import audit
        buckets=audit()['representative_buckets'];self.assertEqual(len(buckets),32)
        for bucket in buckets:
            template=bucket['samples'][0]['template'];capacity=bucket['key'][2]
            with self.subTest(bucket=bucket['key'],template=template),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'save.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
                slots=[0]*4;quantities={};total_cost=0
                for slot in range(capacity):
                    target=1 if slot%2==0 else 4;q=attribute_quote(template,slots,target)
                    quantities[q['material']['template']]=quantities.get(q['material']['template'],0)+q['material']['quantity']
                    total_cost+=q['normal_ed_cost'];slots[slot]=target
                with closing(sqlite3.connect(path)) as db,db:
                    gear=grant_items(db,[dict(template=template,metadata=1,quantity=1,group=1)])[0]
                    for t,n in quantities.items():
                        for offset in range(0,n,99):
                            grant_items(db,[dict(template=t,metadata=2,quantity=min(99,n-offset),group=4)])
                    db.execute('UPDATE reward_balances SET ed=100000000 WHERE uid=1001')
                for slot in range(capacity):
                    result=change_attribute(path,1001,struct.pack('>QBB',gear['uid'],slot,slots[slot]),f'add-{slot}')
                actual=next(i for i in result['inventory'] if i['uid']==gear['uid'])
                self.assertEqual(actual['attributes'],slots)
                self.assertEqual(result['balances']['ed'],100000000-total_cost)
                self.assertFalse(any(i['template'] in quantities for i in result['inventory']))
                snapshot=account.get_inventory_snapshot()
                reloaded=LocalAccount(LocalState(path));reloaded.enable_characters()
                self.assertEqual(reloaded.get_inventory_snapshot(),snapshot)
                with self.assertRaises(ValueError):change_attribute(path,1001,struct.pack('>QBB',gear['uid'],0,1),'full')
                self.assertEqual(account.get_inventory_snapshot(),snapshot)
                for slot in reversed(range(capacity)):
                    result=change_attribute(path,1001,struct.pack('>QBB',gear['uid'],slot,0),f'remove-{slot}')
                actual=next(i for i in result['inventory'] if i['uid']==gear['uid'])
                self.assertEqual(actual.get('attributes',[0]*4),[0]*4)
                with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('PRAGMA quick_check').fetchone(),('ok',))

if __name__=='__main__':unittest.main()
