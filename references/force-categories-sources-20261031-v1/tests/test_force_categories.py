"""Exercise real storage and wire producers against an explicitly selected runtime."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import argparse,collections,json,sqlite3,struct,sys,tempfile,unittest

HOME=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,default=HOME/'candidate')
args,remaining=parser.parse_known_args();sys.path.insert(0,str(args.runtime.resolve()))
PACKETS=[]
from els_server.domain.boosting_2026_force_inventory import catalog,vector
from els_server.domain.boosting_2026_force_equipment import changed,vectors
from els_server.domain.skill_rules import equippable_skills,learned_skills
from els_server.domain.skill_state import equip_request,validate_slots
from els_server.domain.character_rules import validate_career_state
from els_server.game_data import client_data
from els_server.storage.boosting_2026_force_inventory import use_book
from els_server.storage.boosting_2026_force_equipment import action

def role(rule=None):
    data=client_data();cls=(rule or {}).get('unit_class',150);family=data.unit(cls)['unitType']
    return dict(uid=1001,account_id=1,unit_type=family,unit_class=cls,level=99,transcendence=True,master=True,
        artifact=dict(template=family,evolution=4,level=1,experience=0,potentials=[0]*4),
        skill_row_expanded=True,skill_seal_groups=list(range(1,12)),force_slots=((0,0),)*11,
        force_inventory=[] if rule is None else [dict(skill=rule['skill'],rank=rule['native_rank'],template=rule['item'])])

class ForceCategories(unittest.TestCase):
    def setUp(self):
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        self.temp=tempfile.TemporaryDirectory(prefix='owned-force-',dir=HOME);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'state.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters();self.account.enable_inventory()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=1001')
            db.execute("INSERT OR REPLACE INTO character_artifacts VALUES(1001,1,1,1,0,'[0,0,0,0]')")
        validate_career_state(self.account.character())

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return tuple(db.iterdump())

    def grant_book(self,template):
        from els_server.domain.reward_rules import item_plan
        from els_server.storage.inventory_state import grant_items
        with closing(sqlite3.connect(self.path)) as db,db:
            item=grant_items(db,[item_plan(template,1)],1001)[0]
        return struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)

    def learn(self,template):
        payload=self.grant_book(template)
        result=use_book(self.path,1001,1,payload,'learn-'+str(template),now=1900000000)
        self.assertFalse(result['replayed'])
        self.assertEqual([e.kind for e in result['events']],[0x21a,0x6cb])
        PACKETS.extend(dict(kind=e.kind,payload=e.payload.hex())for e in result['events']if e.kind==0x6cb)
        return payload

    def test_common_active_learning_equip_and_cold_read(self):
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        payload=self.learn(295734)
        self.account.equip_skill(struct.pack('>ii',0,900224))
        self.assertEqual(LocalAccount(LocalState(self.path)).get_skills()[0],900224)
        before=self.dump()
        self.assertTrue(use_book(self.path,1001,1,payload,'learn-295734',now=1900000000)['replayed'])
        self.assertEqual(self.dump(),before)

    def test_common_active_kept_when_equipping_passive_and_mod(self):
        self.learn(295734);self.learn(295712);self.learn(300550)
        self.account.equip_skill(struct.pack('>ii',0,900224))
        for kind,index,skill,rank in ((1,0,900402,3),(2,0,901012,1)):
            payload=struct.pack('>iiiB',kind,index,skill,rank)
            event=action(self.path,1001,1,payload,'equip-'+str(skill))
            PACKETS.append(dict(kind=event.kind,payload=event.payload.hex()))
            self.assertEqual((event.kind,event.payload[:4]),(0x6d1,bytes(4)))
            before=self.dump();action(self.path,1001,1,payload,'equip-'+str(skill));self.assertEqual(self.dump(),before)
        self.assertEqual(self.account.store.load_skills()[0],900224)
        c=self.account.character();self.assertEqual(c['force_slots'][0],(900402,3));self.assertEqual(c['force_slots'][3],(901012,1))
        from els_server.protocol.dungeon_messages import skill_data
        self.assertTrue(skill_data(self.account.get_skills(),c).endswith(vector(c)+b'\0'))
        self.assertEqual(self.account.character_list()[0]['force_inventory'],c['force_inventory'])
        before=self.dump()
        with patch('els_server.storage.boosting_2026_force_equipment._commit',side_effect=ValueError('injected commit failure')):
            with self.assertRaisesRegex(ValueError,'injected commit failure'):
                action(self.path,1001,1,struct.pack('>iiiB',1,1,900402,3),'rollback')
        self.assertEqual(self.dump(),before)

    def test_five_native_core_positions_and_locked_rows(self):
        self.learn(295734)
        for index in range(10,15):
            ack=self.account.equip_skill(struct.pack('>ii',index,900224))
            PACKETS.append(dict(kind=0x123,payload=ack.hex()))
            self.assertEqual(self.account.store.load_skills()[index],900224)
        for index in (5,15,19,20,21):
            before=self.dump()
            with self.assertRaises(ValueError):self.account.equip_skill(struct.pack('>ii',index,900224))
            self.assertEqual(self.dump(),before)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('DELETE FROM skill_slots WHERE uid=1001')
            db.execute('UPDATE characters SET unit_class=1,transcendence=0,master=0 WHERE uid=1001')
            db.execute('DELETE FROM character_artifacts WHERE uid=1001')
        with self.assertRaises(ValueError):self.account.equip_skill(struct.pack('>ii',10,900224))

    def test_active_and_ordinary_capacity(self):
        c=role();rules=list(catalog().values());actives=[r for r in rules if r.get('active')]
        c['force_inventory']=[dict(skill=r['skill'],rank=r['native_rank'],template=r['item'])for r in actives]
        allowed=equippable_skills(c);slots=(0,)*22
        for index,r in zip(range(10,15),actives):slots,_=equip_request(struct.pack('>ii',index,r['skill']),slots,allowed,c)
        with self.assertRaises(ValueError):equip_request(struct.pack('>ii',0,actives[5]['skill']),slots,allowed,c)
        normal=[s for s in allowed if client_data().skill(s)['m_eType'] not in (13,20,22,23,24,25)]
        self.assertGreaterEqual(len(normal),11)
        slots=tuple(normal[:10])+(0,)*12;validate_slots(slots,allowed,c)
        with self.assertRaises(ValueError):equip_request(struct.pack('>ii',10,normal[10]),slots,allowed,c)

    def test_book_failure_rolls_back_and_qualification_rejects(self):
        payload=self.grant_book(295734);before=self.dump()
        with patch('els_server.storage.boosting_2026_force_inventory._commit',side_effect=ValueError('injected book failure')):
            with self.assertRaisesRegex(ValueError,'injected book failure'):
                use_book(self.path,1001,1,payload,'failure',now=1900000000)
        self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):use_book(self.path,1001,2,payload,'wrong-owner',now=1900000000)
        self.assertEqual(self.dump(),before)
        use_book(self.path,1001,1,payload,'qualified',now=1900000000)

    def test_passive_third_slot_requires_artifact_and_master(self):
        r=catalog()[295712];c=role(r)
        c['artifact']['evolution']=1
        with self.assertRaises(ValueError):changed(c,struct.pack('>iiiB',1,2,r['skill'],r['native_rank']))
        c['artifact']['evolution']=4
        self.assertEqual(changed(c,struct.pack('>iiiB',1,2,r['skill'],r['native_rank']))[2],(r['skill'],r['native_rank']))

    def test_catalog_all_categories_and_native_projection(self):
        counts=collections.Counter();data=client_data()
        for template,r in catalog().items():
            c=role(r);validate_career_state(c);sid=r['skill'];rank=r['native_rank']
            self.assertEqual(struct.unpack('>IiBiB',vector(c)),(1,sid,rank,0,0))
            if r.get('change'):
                self.assertEqual(data.skill(sid)['m_eType'],18)
                updated=changed(c,struct.pack('>iiiB',2,7,sid,rank));self.assertEqual(updated[10],(sid,rank))
                with self.assertRaises(ValueError):changed(dict(c,unit_class=164 if c['unit_class']!=164 else 150),struct.pack('>iiiB',2,7,sid,rank))
                counts['mod_books']+=1
            elif r.get('active'):
                self.assertEqual(data.skill(sid)['m_eType'],20)
                slots,_=equip_request(struct.pack('>ii',10,sid),(0,)*22,equippable_skills(c),c);self.assertEqual(slots[10],sid)
                from els_server.domain.role_progression import known_skills
                self.assertIn(sid,known_skills(c['unit_class']))
                if r.get('required_master'):self.assertNotIn(sid,equippable_skills(dict(c,master=False,artifact=None)))
                counts['active_books']+=1
                continue
            else:
                self.assertEqual(data.skill(sid)['m_eType'],17)
                updated=changed(c,struct.pack('>iiiB',1,2,sid,rank));self.assertEqual(updated[2],(sid,rank));counts['passive_books']+=1
            c['force_slots']=updated;self.assertEqual(len(vectors(c)),74)
            self.assertFalse(any(s for s,_ in changed(c,struct.pack('>iiiB',0,0,sid,rank))))
        (HOME/'catalog-validation.json').write_text(json.dumps(dict(ok=True,counts=counts,unique_skills=len({r['skill']for r in catalog().values()}),natural_battle=False),indent=2),encoding='utf8')

if __name__=='__main__':
    result=unittest.main(argv=[sys.argv[0],*remaining],verbosity=2,exit=False)
    if result.result.wasSuccessful():
        (HOME/'synthetic-packets.json').write_text(json.dumps(PACKETS),encoding='utf8')
    raise SystemExit(not result.result.wasSuccessful())
