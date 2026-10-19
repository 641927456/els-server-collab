"""Native ordinary/TC slot categories follow separate persisted role conditions."""
import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from els_server.domain.skill_expansion import unlocked_indices
from els_server.domain.character_rules import CLASSES
from els_server.domain.skill_rules import equippable_skills
from els_server.domain.skill_state import equip_request
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.storage.careers import use_career_item
from els_server.domain.careers import RULES


class TranscendenceSlotTests(unittest.TestCase):
    def test_native_stage_matrix_for_every_class(self):
        for cls,meta in CLASSES.items():
            for ordinary in (False,True):
                for transcendence in (False,True):
                    c=dict(unit_class=cls,level=99,transcendence=transcendence,skill_row_expanded=ordinary)
                    expected={0,1,2,3}|({5,6,7,8} if ordinary else set())|({4,9} if transcendence and meta['stage']>=2 else set())
                    self.assertEqual(set(unlocked_indices(c)),expected,(cls,ordinary,transcendence))
        self.assertEqual(set(unlocked_indices(dict(unit_class=150,master=True))),{0,1,2,3,4,9,21})

    def test_no_extra_coupon_or_ordinary_row_required(self):
        c=dict(unit_class=100,level=99,transcendence=True)
        allowed=equippable_skills(c);slots=(0,)*22
        for index in (4,9):
            slots,ack=equip_request(struct.pack('>ii',index,allowed[0]),slots,allowed,c)
            self.assertEqual(slots[index],allowed[0]);self.assertEqual(struct.unpack_from('>i',ack)[0],0)
        for index in (5,6,7,8,10,14,19,20,21):
            with self.assertRaises(ValueError):equip_request(struct.pack('>ii',index,allowed[0]),slots,allowed,c)

    def test_career_unlock_layout_persistence_and_third_job(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters()
            with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE characters SET level=99,unit_class=100 WHERE uid=1001')
            skill=equippable_skills(a.character())[0]
            with self.assertRaises(ValueError):a.equip_skill(struct.pack('>ii',4,skill))
            for kind,target in [('transcendence_book',0),('advancement_3',150)]:
                template=next(t for t,r in RULES.items() if r['kind']==kind and r['target']==target)
                with closing(sqlite3.connect(path)) as db,db:
                    item=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=4,quantity=1)])[0]
                use_career_item(path,1001,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0),kind)
                if kind=='transcendence_book':
                    allowed=equippable_skills(a.character())
                    a.equip_skill(struct.pack('>ii',4,allowed[0]));a.equip_skill(struct.pack('>ii',9,allowed[1]))
                else:
                    self.assertNotEqual(a.get_skills()[4],0);self.assertNotEqual(a.get_skills()[9],0)
            restored=LocalAccount(LocalState(path));restored.enable_characters()
            self.assertEqual(restored.get_skills(),a.get_skills())
            self.assertFalse(restored.character()['skill_row_expanded'])


if __name__=='__main__':unittest.main()
