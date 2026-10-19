"""Create grants, full native routes, dedicated Master slots and rollback."""
import json,sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters,DEFAULT_CHARACTER
from els_server.storage.inventory_state import grant_items
from els_server.storage.careers import use_career_item
from els_server.domain.careers import RULES,PARENTS
from els_server.domain.character_rules import default_slots,artifact_wire
from els_server.domain.role_progression import catalog,first_master_skill
from els_server.domain.skill_rules import learned_skills,equippable_skills
from els_server.domain.skill_state import encode_slots,equip_request
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.fashion_state import move_fashion
from els_server.game_data import client_data


class RoleProgressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def ticket(self,template,owner=1001):
        with closing(sqlite3.connect(self.path)) as db,db:
            item=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],quantity=1,group=TEMPLATE_BAG_GROUPS[template])],owner)[0]
        return struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)

    def test_creation_15_roles_replay_equipment_and_reopen(self):
        seen=set();original=self.account.get_inventory_snapshot()
        for role in range(1,16):
            c=self.account.characters.create('新角色'+str(role),role,'create-'+str(role));a=self.account.for_character(c['uid'])
            snap=a.get_inventory_snapshot();expected=catalog()['roles'][str(role)]
            self.assertEqual({i['template'] for i in snap['items']},set(expected['equipment']+expected['costumes']+expected['alternate_costumes']))
            self.assertEqual(len([i for i in snap['items'] if i['group']==9]),10)
            self.assertTrue(all(i.get('durability',10000)==10000 and i['count']==1 for i in snap['items']))
            self.assertFalse(seen&{i['uid'] for i in snap['items']});seen.update(i['uid'] for i in snap['items'])
            before=self.dump();self.assertEqual(self.account.characters.create(c['name'],role,'create-'+str(role)),c)
            self.assertEqual(self.dump(),before)
            reopened=LocalAccount(LocalState(self.path,c['uid']));reopened.enable_characters()
            self.assertEqual(reopened.get_inventory_snapshot(),snap);self.assertEqual(reopened.get_skills(),a.get_skills())
        self.assertEqual(self.account.get_inventory_snapshot(),original)

    def test_creation_encoder_failure_rolls_back_identity_items_and_sequence(self):
        before=self.dump()
        with patch('els_server.protocol.character_messages.create_ack',side_effect=ValueError('codec fail')):
            with self.assertRaises(ValueError):self.account.characters.create('编码回滚',15,'failed')
        self.assertEqual(self.dump(),before)
        c=self.account.characters.create('编码成功',15,'failed');self.assertEqual(c['uid'],1002)

    def test_old_created_character_gets_missing_kit_once_without_replacing_assets(self):
        c=self.account.characters.create('旧建伊芙',5,'old-create');uid=c['uid']
        with closing(sqlite3.connect(self.path)) as db,db:
            # Reproduce an old character missing its costume, with later gear
            # already worn. Existing UID, durability and location must survive.
            db.execute('DELETE FROM inventory_items WHERE owner=? AND bag_group=9 AND slot=2',(uid,))
            db.execute('DELETE FROM character_loadout_receipts WHERE owner=?',(uid,))
            extra=grant_items(db,[dict(template=128001,metadata=0,group=7,quantity=1)],uid)[0]
        before=self.account.for_character(uid).get_inventory_snapshot()
        reopened=LocalAccount(LocalState(self.path));reopened.enable_characters()
        after=reopened.for_character(uid).get_inventory_snapshot()
        self.assertEqual(len(after['items']),len(before['items'])+1)
        self.assertTrue(all(i in after['items'] for i in before['items']))
        self.assertEqual(after['balances'],before['balances'])
        self.assertEqual(reopened.initial_loadout_repair,dict(repaired=[uid],deferred=[]))
        reopened.enable_characters();self.assertEqual(reopened.initial_loadout_repair,dict(repaired=[],deferred=[]))
        self.assertEqual(reopened.for_character(uid).get_inventory_snapshot(),after)

    def test_full_bag_defers_old_kit_without_partial_grant_then_can_retry(self):
        from els_server.storage.role_loadout import repair_created_loadouts
        c=self.account.characters.create('满包伊芙',5,'full-old');uid=c['uid']
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('DELETE FROM inventory_items WHERE owner=? AND bag_group=9 AND slot=2',(uid,))
            db.execute('DELETE FROM character_loadout_receipts WHERE owner=?',(uid,))
            grant_items(db,[dict(template=128001,metadata=0,group=7,quantity=36)],uid)
        before=self.dump()
        self.assertEqual(repair_created_loadouts(self.path),dict(repaired=[],deferred=[uid]));self.assertEqual(self.dump(),before)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('DELETE FROM inventory_items WHERE owner=? AND bag_group=7 AND slot=0',(uid,))
        self.assertEqual(repair_created_loadouts(self.path),dict(repaired=[uid],deferred=[]))

    def test_old_kit_never_replaces_a_player_selected_costume(self):
        from els_server.storage.role_loadout import repair_created_loadouts
        from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
        c=self.account.characters.create('已有时装',5,'custom');uid=c['uid']
        custom=next(t for t,s in FASHION_EQUIP_SLOTS.items() if s==2 and t!=130135 and client_data().item(t)['record'][210]==5)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('DELETE FROM inventory_items WHERE owner=? AND bag_group=9 AND slot=2',(uid,))
            db.execute('DELETE FROM character_loadout_receipts WHERE owner=?',(uid,))
            item=grant_items(db,[dict(template=custom,metadata=VERIFIED_TEMPLATES[custom],group=TEMPLATE_BAG_GROUPS[custom],quantity=1)],uid)[0]
            db.execute('UPDATE inventory_items SET bag_group=9,slot=2 WHERE uid=?',(item['uid'],))
        before=self.account.for_character(uid).get_inventory_snapshot()['items']
        self.assertEqual(repair_created_loadouts(self.path),dict(repaired=[uid],deferred=[]))
        after=self.account.for_character(uid).get_inventory_snapshot()['items']
        self.assertTrue(all(i in after for i in before))
        self.assertTrue(any(i['template']==130135 and i['group']==7 for i in after))

    def test_all_60_routes_commit_every_stage_and_restore_master_skill(self):
        for cls,grades in catalog()['master_skills'].items():
            target=int(cls);second=PARENTS[target];first=PARENTS[second];base=PARENTS[first]
            from els_server.game_data import client_data
            role=client_data().unit(base)['unitType']
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('UPDATE characters SET unit_type=?,unit_class=?,level=99,transcendence=0,master=0 WHERE uid=1001',(role,base))
                db.execute('DELETE FROM character_artifacts WHERE uid=1001');db.execute('DELETE FROM skill_slots WHERE uid=1001')
            self.account.save_skills(default_slots(self.account.character()))
            for index,(kind,wanted) in enumerate((('advancement_1',first),('advancement_2',second),('transcendence_book',0),('advancement_3',target),('master_advancement',target))):
                t=next(t for t,r in RULES.items() if r['kind']==kind and r['target']==wanted)
                payload=self.ticket(t);operation=f'route-{target}-{index}'
                receipt=use_career_item(self.path,1001,payload,operation)
                self.assertFalse(receipt['replayed']);before=self.dump()
                self.assertTrue(use_career_item(self.path,1001,payload,operation)['replayed']);self.assertEqual(self.dump(),before)
            character=Characters(self.path).get(1001);self.assertTrue(character['master']);self.assertEqual(character['artifact']['template'],role)
            self.assertEqual(first_master_skill(character),grades['0'])
            self.assertEqual(set(learned_skills(character))&set(grades.values()),{grades['0']})
            store=LocalState(self.path);slots=store.load_skills();self.assertEqual(slots[21],grades['0'])
            store.save_skills(slots);self.assertEqual(LocalState(self.path).load_skills(),slots)
            self.assertEqual(len(artifact_wire(character)),40)

    def test_master_route_change_replaces_skill_and_preserves_artifact(self):
        artifact=dict(template=1,evolution=2,level=7,experience=125,potentials=[1,2,3,4])
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=1001')
            db.execute('INSERT INTO character_artifacts VALUES (1001,1,2,7,125,?)',(json.dumps(artifact['potentials']),))
        c=self.account.character();self.account.save_skills(default_slots(c))
        target=next(int(k) for k in catalog()['master_skills'] if int(k)!=150 and client_data().unit(int(k))['unitType']==1)
        t=next(t for t,r in RULES.items() if r['kind']=='master_change' and r['target']==target)
        use_career_item(self.path,1001,self.ticket(t),'master-change')
        c=self.account.character();self.assertEqual(c['artifact'],artifact)
        self.assertEqual(self.account.get_skills()[21],first_master_skill(c));self.assertNotEqual(self.account.get_skills()[21],801001)

    def test_existing_master_preset_recovers_once_and_keeps_later_empty_choice(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=1001')
            db.execute('INSERT INTO character_artifacts VALUES (1001,1,1,1,0,?)',(json.dumps([0]*4),))
            db.execute('INSERT INTO skill_slots VALUES (1001,?,0)',(struct.pack('>22i',21026,21217,*([0]*20)),))
        reopened=LocalAccount(LocalState(self.path));reopened.enable_characters()
        self.assertEqual(reopened.master_preset_repair,[1001]);self.assertEqual(reopened.get_skills()[21],801001)
        reopened.equip_skill(struct.pack('>ii',21,0))
        reopened=LocalAccount(LocalState(self.path));reopened.enable_characters()
        self.assertEqual(reopened.master_preset_repair,[]);self.assertEqual(reopened.get_skills()[21],0)

    def test_master_skill_is_confined_to_master_slot(self):
        c=dict(DEFAULT_CHARACTER,unit_class=150,level=99,master=True,transcendence=True)
        slots=default_slots(c);allowed=equippable_skills(c);master=first_master_skill(c)
        for index in (0,1,4,9,20):
            with self.assertRaises(ValueError):equip_request(struct.pack('>ii',index,master),slots,allowed,c)
        with self.assertRaises(ValueError):equip_request(struct.pack('>ii',21,allowed[0]),slots,allowed,c)
        empty,_=equip_request(struct.pack('>ii',21,0),slots,allowed,c);self.assertEqual(empty[21],0)
        self.assertEqual(encode_slots(empty,allowed,c)[84:88],bytes(4))

    def test_foreign_role_fashion_cannot_be_worn_or_swapped(self):
        c=self.account.characters.create('伊芙衣服',5,'create-eve');a=self.account.for_character(c['uid'])
        with closing(sqlite3.connect(self.path)) as db,db:
            item=grant_items(db,[dict(template=128001,metadata=0,group=7,quantity=1)],c['uid'])[0]
        before=a.get_inventory_snapshot()
        with self.assertRaises(ValueError):move_fashion(self.path,struct.pack('>BiBiB',7,item['slot'],9,2,0),c['uid'])
        self.assertEqual(a.get_inventory_snapshot(),before)

    def test_bad_artifact_fields_and_missing_artifact_fail_before_career_consumption(self):
        c=dict(DEFAULT_CHARACTER,unit_class=150,level=99,master=True,transcendence=True)
        for artifact in (None,dict(template=1,evolution=5,level=10,experience=0,potentials=[0]*4),dict(template=1,evolution=1,level=1,experience=0,potentials=[2**31,0,0,0])):
            with self.assertRaises(ValueError):artifact_wire(dict(c,artifact=artifact))
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=1001')
        t=next(t for t,r in RULES.items() if r['kind']=='master_change' and r['unit_type']==1 and r['target']!=150)
        payload=self.ticket(t);before=self.dump()
        with self.assertRaises(ValueError):use_career_item(self.path,1001,payload,'invalid-master')
        self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main()
