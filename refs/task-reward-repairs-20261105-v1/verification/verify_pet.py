"""Actual private quest reward -> nutritional clock -> digestive use, no live game."""
import json,sqlite3,struct,unittest
from contextlib import closing
from unittest.mock import patch
import verify_furniture as harness
from verify_furniture import Consumers,encode,item_use,checks,PRIVATE,OUT,BASE,temp
from els_server.storage import companion_state,pet_progression,pet_nutrition
from els_server.protocol.local_messages import wstring
from els_server.domain.pet_progression import template

class Pets(Consumers):
    def create_pet(self,full=True):
        egg=self.grant(500051)[0]
        encode(companion_state.handle(self.path,self.uid,0x2e8,struct.pack('>Q',egg['uid'])+wstring('OwnPet'),'pet-create'))
        pet=companion_state.snapshot(self.path,self.uid)['companions'][0]
        if full:
            pet.update(step=template(pet['unit'])['EVOLUTION_ALL_STEP'],growth=0)
            with closing(sqlite3.connect(self.path))as db,db:pet_progression.save(db,self.uid,pet)
        return pet
    def current_pet(self):return companion_state.snapshot(self.path,self.uid)['companions'][0]
    def nutrient_request(self,pet,item,count=1):return struct.pack('>IQiQB',1,item['uid'],count,pet['uid'],1)
    def use(self,kind,payload,operation,now=2000000000):
        return pet_nutrition.perform(self.path,self.uid,1,kind,payload,operation,self.guard,now=now)
    def test_source_reward_digestion(self):
        pet=self.create_pet();self.ready(25610);source=self.claim(25610)
        medicine=next(i for i in source['updates']if i['template']==135994)
        self.assertEqual(medicine['count'],3)
        payload=struct.pack('>Qi',pet['uid'],135994)
        before=self.dump()
        with self.assertRaises(ValueError):self.use(0x8b9,payload,'empty-digest')
        self.assertEqual(before,self.dump())
        food=self.grant(135977)[0];nutrient=self.nutrient_request(pet,food)
        before=self.dump()
        with patch('els_server.storage.pet_nutrition.encode_event',side_effect=ValueError('owned late encoding fault')):
            with self.assertRaises(ValueError):self.use(0x8ad,nutrient,'nutrient')
        self.assertEqual(before,self.dump())
        events=self.use(0x8ad,nutrient,'nutrient');encode(events)
        pet=self.current_pet();self.assertEqual((pet['nutrition'],pet['digest_until']),(1,2000010800))
        # Replay updates the current contents of the old food slot.
        replacement=self.grant(135977)[0];before=self.dump()
        replay=self.use(0x8ad,nutrient,'nutrient',now=2000000060);encode(replay)
        self.assertEqual(before,self.dump());self.assertIn(struct.pack('>I',135977),replay[0].payload)
        before=self.dump()
        with patch('els_server.storage.pet_nutrition.encode_event',side_effect=ValueError('owned digest encoding fault')):
            with self.assertRaises(ValueError):self.use(0x8b9,payload,'digest')
        self.assertEqual(before,self.dump())
        events=self.use(0x8b9,payload,'digest');encode(events)
        self.assertEqual(self.current_pet()['digest_until'],2000003600)
        self.assertEqual(next(i for i in self.items()if i['uid']==medicine['uid'])['count'],2)
        before=self.dump();encode(self.use(0x8b9,payload,'digest',now=2000000060));self.assertEqual(before,self.dump())
        encode(self.use(0x8b9,payload,'digest-rest'))
        self.assertEqual(self.current_pet()['digest_until'],2000000000)
        self.assertEqual(next(i for i in self.items()if i['uid']==medicine['uid'])['count'],1)
        before=self.dump()
        with self.assertRaises(ValueError):self.use(0x8b9,payload,'no-more-time')
        self.assertEqual(before,self.dump())
        checks.append(dict(case='quest25610_digestive_use',actual_reward=135994,initial_count=3,native_nutrient_hours=3,lower_digest_hours=2,
                           cold_saved_deadline=True,rollback_both_paths=True,replay_both_paths=True,replacement_slot_preserved=True,zero_time_no_debit=True))
    def test_nutrient_capacity_and_ownership(self):
        pet=self.create_pet();food=self.grant(135977,57)[0];payload=self.nutrient_request(pet,food,57)
        before=self.dump()
        with self.assertRaises(ValueError):self.use(0x8ad,payload,'over-cap')
        self.assertEqual(before,self.dump())
        encode(self.use(0x8ad,self.nutrient_request(pet,food,56),'exact-cap'))
        self.assertEqual(self.current_pet()['digest_until'],2000000000+168*3600)
        self.assertEqual(next(i for i in self.items()if i['uid']==food['uid'])['count'],1)
        before=self.dump()
        with self.assertRaises(ValueError):self.use(0x8ad,self.nutrient_request(pet,food),'full')
        self.assertEqual(before,self.dump())
        medicine=self.grant(135994)[0]
        for bad in(struct.pack('>Qi',pet['uid']+1,135994),struct.pack('>Qi',pet['uid'],135993)):
            before=self.dump()
            with self.assertRaises(ValueError):self.use(0x8b9,bad,'bad-'+bad.hex())
            self.assertEqual(before,self.dump())
        from els_server.storage.item_locks import assign
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,self.uid,medicine['uid'],2000003600)
        before=self.dump()
        with self.assertRaises(ValueError):self.use(0x8b9,struct.pack('>Qi',pet['uid'],135994),'locked')
        self.assertEqual(before,self.dump())
        checks.append(dict(case='pet_nutrient_limits',exact_168_hours=True,overflow_atomic=True,foreign_pet_rejected=True,wrong_template_rejected=True,locked_medicine_no_debit=True))

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromNames(['Pets.test_source_reward_digestion','Pets.test_nutrient_capacity_and_ownership'],module=__import__(__name__))
    result=unittest.TextTestRunner(verbosity=2).run(suite);temp.cleanup()
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,checks=checks,failures=[dict(test=str(t),trace=e)for t,e in result.failures+result.errors],
                private_SQL_removed=not PRIVATE.exists(),network=False,formal_SQL=False,natural_GUI=False)
    (OUT/'pet-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(ok=report['ok'],private_SQL_removed=report['private_SQL_removed'])))
    raise SystemExit(0 if report['ok']else 1)
