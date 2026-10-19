"""Seal books remain character-owned, transactional and native-stage gated."""
import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.skill_unlocks import use_skill_book
from els_server.storage.inventory_state import grant_items
from els_server.domain.skill_unlocks import catalog,unsealed_skills,eligible_skills,validate_unlock
from els_server.domain.skill_rules import learned_skills,equippable_skills,upgraded_slots
from els_server.domain.skill_state import equip_request
from els_server.domain.role_progression import catalog as roles,master_skills
from els_server.domain.character_rules import CLASSES
from els_server.protocol.protocol_codec import Event
from els_server.game_data import client_data

class SkillUnlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'test.db';self.a=LocalAccount(LocalState(self.path));self.a.enable_characters()

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def book(self,group,uid=1001,template=None):
        row=next(r for r in catalog()['books'].values() if r['seal_group']==group and (template is None or r['template']==template))
        with closing(sqlite3.connect(self.path)) as db,db:
            item=grant_items(db,[dict(template=row['template'],metadata=0,group=4,quantity=1)],uid)[0]
        return struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)

    def set_class(self,cls,uid=1001,level=99,tc=True,master=True):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=?,level=?,transcendence=?,master=? WHERE uid=?',(cls,level,tc,master,uid))
            if master:
                typ=db.execute('SELECT unit_type FROM characters WHERE uid=?',(uid,)).fetchone()[0]
                db.execute("INSERT OR REPLACE INTO character_artifacts VALUES (?,?,1,1,0,'[0,0,0,0]')",(uid,typ))

    def test_all_native_groups_and_aliases_are_covered_without_fabrication(self):
        self.assertEqual(len(catalog()['books']),69);self.assertEqual(len(catalog()['missing_templates']),10)
        self.assertEqual(set(catalog()['groups']),{str(n) for n in range(1,12)})
        for group in range(1,12):self.assertTrue(any(r['seal_group']==group for r in catalog()['books'].values()))
        self.assertEqual(len({s for r in catalog()['groups'].values() for s in r['skills']}),751)

    def test_every_present_book_alias_consumes_and_unlocks_its_native_group(self):
        self.set_class(150)
        for row in catalog()['books'].values():
            # Independent fixture for each alias, with Master prerequisites.
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('CREATE TABLE IF NOT EXISTS character_skill_seals (owner INTEGER NOT NULL, seal_group INTEGER NOT NULL, PRIMARY KEY(owner,seal_group))')
                db.execute('DELETE FROM character_skill_seals')
                for group in range(9,row['seal_group']):db.execute('INSERT INTO character_skill_seals VALUES (1001,?)',(group,))
            payload=self.book(row['seal_group'],template=row['template'])
            receipt=use_skill_book(self.path,1001,payload,'alias-'+str(row['template']))
            self.assertFalse(receipt['replayed']);self.assertIn(row['seal_group'],self.a.character()['skill_seal_groups'])

    def test_all_60_routes_keep_seals_and_unlock_only_purchased_group(self):
        for cls in roles()['master_skills']:
            c=dict(unit_class=int(cls),level=99,transcendence=True,master=True)
            base=learned_skills(c);self.assertEqual(set(master_skills(int(cls)))&base.keys(),{master_skills(int(cls))[0]})
            unlocked=[]
            for group in range(1,12):
                validate_unlock(dict(c,skill_seal_groups=tuple(unlocked)),group)
                unlocked.append(group);after=dict(c,skill_seal_groups=tuple(unlocked))
                self.assertTrue(set(eligible_skills(c,group))<=set(unsealed_skills(after)))
                self.assertTrue(set(unsealed_skills(after))<={s for g in unlocked for s in catalog()['groups'][str(g)]['skills']})
            self.assertTrue(set(master_skills(int(cls)))<=learned_skills(after).keys())
            self.assertTrue(any(client_data().skill(s)['m_eType']==13 for s in equippable_skills(after)))

    def test_level_class_tc_master_and_grade_prerequisites(self):
        for cls,meta in CLASSES.items():
            for group in range(1,12):
                c=dict(unit_class=cls,level=1,transcendence=False,master=False)
                with self.assertRaises(ValueError):validate_unlock(c,group)
                if meta['stage']<catalog()['groups'][str(group)]['stage']:
                    with self.assertRaises(ValueError):validate_unlock(dict(c,level=99),group)
        c=dict(unit_class=150,level=99,transcendence=True,master=True)
        for group in (10,11):
            with self.assertRaises(ValueError):validate_unlock(c,group)
        with self.assertRaises(ValueError):validate_unlock(dict(c,master=False),9)
        with self.assertRaises(ValueError):validate_unlock(dict(c,transcendence=False),6)

    def test_use_persistence_hyper_slot_duplicate_and_retry_current_inventory(self):
        self.set_class(150)
        payload=self.book(5);before=self.a.get_inventory_snapshot()
        receipt=use_skill_book(self.path,1001,payload,'unlock')
        self.assertEqual(receipt['notification'].kind,0x131);self.assertFalse(receipt['replayed'])
        c=self.a.character();self.assertEqual(c['skill_seal_groups'],(5,))
        hyper=next(s for s in equippable_skills(c) if client_data().skill(s)['m_eType']==13)
        slots,ack=equip_request(struct.pack('>ii',20,hyper),self.a.get_skills(),equippable_skills(c),c);self.a.save_skills(slots)
        self.assertEqual(self.a.for_character(1001).get_skills()[20],hyper)
        reopened=LocalAccount(LocalState(self.path));reopened.enable_characters()
        self.assertEqual(reopened.get_skills()[20],hyper);self.assertEqual(reopened.character()['skill_seal_groups'],(5,))
        replacement=self.book(1);snap=self.dump()
        self.assertTrue(use_skill_book(self.path,1001,payload,'unlock')['replayed']);self.assertEqual(self.dump(),snap)
        with self.assertRaises(ValueError):use_skill_book(self.path,1001,replacement,'unlock')
        duplicate=self.book(5);snap=self.dump()
        with self.assertRaises(ValueError):use_skill_book(self.path,1001,duplicate,'duplicate')
        self.assertEqual(self.dump(),snap)
        self.assertEqual(len(self.a.get_inventory_snapshot()['items']),len(before['items'])+1)

    def test_wrong_owner_expired_and_serialization_failure_do_not_consume(self):
        self.set_class(150);payload=self.book(9);other=self.a.characters.create('其他角色',2,'other')
        snap=self.dump();self.assertIsNone(use_skill_book(self.path,other['uid'],payload,'foreign'));self.assertEqual(self.dump(),snap)
        with patch('els_server.domain.item_expiration.require_current',side_effect=ValueError('expired')):
            with self.assertRaises(ValueError):use_skill_book(self.path,1001,payload,'expire')
        self.assertEqual(self.dump(),snap)
        with patch('els_server.domain.skill_unlocks.unlock_notice',side_effect=ValueError('encoding failure')):
            with self.assertRaises(ValueError):use_skill_book(self.path,1001,payload,'failed')
        self.assertEqual(self.dump(),snap)
        with patch('els_server.domain.skill_state.initialization_payload',side_effect=ValueError('login encoding failure')):
            with self.assertRaises(ValueError):use_skill_book(self.path,1001,payload,'failed')
        self.assertEqual(self.dump(),snap)
        use_skill_book(self.path,1001,payload,'failed')

    def test_master_grade_kept_through_actual_career_transaction_and_relogin(self):
        from els_server.domain.careers import RULES
        from els_server.storage.careers import use_career_item
        self.set_class(150)
        for group in (9,10,11):use_skill_book(self.path,1001,self.book(group),'master-'+str(group))
        slots=list(self.a.get_skills());slots[21]=master_skills(150)[3];self.a.save_skills(slots)
        target=next(int(k) for k in roles()['master_skills'] if int(k)!=150 and client_data().unit(int(k))['unitType']==1)
        template=next(t for t,r in RULES.items() if r['kind']=='master_change' and r['target']==target)
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES
        with closing(sqlite3.connect(self.path)) as db,db:
            item=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=4,quantity=1)])[0]
        use_career_item(self.path,1001,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0),'master-change')
        self.assertEqual(self.a.get_skills()[21],master_skills(target)[3])
        self.assertEqual(self.a.character()['skill_seal_groups'],(9,10,11))
        reopened=LocalAccount(LocalState(self.path));reopened.enable_characters()
        self.assertEqual(reopened.get_skills()[21],master_skills(target)[3])

    def test_actual_consumption_all_15_roles_and_11_groups_and_master_grade_route_change(self):
        for typ in range(1,16):
            c=self.a.characters.create('解封角色'+str(typ),typ,'role-'+str(typ));uid=c['uid']
            cls=next(int(k) for k in roles()['master_skills'] if client_data().unit(int(k))['unitType']==typ)
            self.set_class(cls,uid)
            for group in range(1,12):
                receipt=use_skill_book(self.path,uid,self.book(group,uid),str(uid)+'-'+str(group))
                self.assertFalse(receipt['replayed'])
            c=self.a.characters.get(uid);self.assertEqual(c['skill_seal_groups'],tuple(range(1,12)))
            choices=[int(k) for k in roles()['master_skills'] if client_data().unit(int(k))['unitType']==typ]
            slots=[0]*22;slots[21]=master_skills(cls)[3]
            mapped=upgraded_slots(slots,dict(c,unit_class=choices[-1]))
            self.assertEqual(mapped[21],master_skills(choices[-1])[3])

    def test_native_session_response_and_duplicate_use_have_no_second_celebration(self):
        self.set_class(150);payload=self.book(9)
        session=LocalSession(self.a,enter_town=True,client_build='dx11_260923');session.item_test=True;session.role='game';session.phase='town_ready'
        before=self.dump();event=Event(0x202,kind=0x219,payload=payload)
        self.assertEqual([e.kind for e in session.handle(event,request_sequence=0)],[0x21a]);self.assertEqual(self.dump(),before)
        self.assertEqual([e.kind for e in session.handle(event,request_sequence=1)],[0x21a,0x131,0x55b])
        snap=self.dump();self.assertEqual([e.kind for e in session.handle(event,request_sequence=1)],[0x21a,0x55b]);self.assertEqual(self.dump(),snap)

if __name__=='__main__':unittest.main()
