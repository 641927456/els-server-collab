"""Threshold unlocks are derived on the shared native item wire, not saved options."""
import copy,sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.enhancement_unlock import options
from els_server.domain.inventory_items import item_body,fixture,inventory_restore_map
from els_server.domain.fashion_state import record,equipment_map
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.equipment_enhancement import replace


def groups(body):
    pos=next(f['wire_offset'] for f in fixture()['fields'] if int(f['offset'],0)==0x25)
    assert struct.unpack_from('>I',body,pos)[0]==33
    pos+=4;result={}
    for group in range(33):
        count=struct.unpack_from('>I',body,pos)[0];pos+=4
        if count:result[str(group)]=list(struct.unpack_from('>'+str(count)+'i',body,pos))
        pos+=4*count
    return result


def armor(template=721897,level=11):
    return dict(uid=9000001,template=template,metadata=1,count=1,group=1,slot=0,
                durability=10000,enhancement=level)


class EnhancementUnlockTests(unittest.TestCase):
    def test_tenebrous_boundaries_and_broken_restore(self):
        for template in (721897,721898,721899,721900):
            for level,expected in ((0,[]),(9,[]),(10,[43510]),(11,[43510,99266]),
                                   (20,[43510,99266]),(-11,[]),(11,[43510,99266])):
                with self.subTest(template=template,level=level):
                    self.assertEqual(groups(item_body(armor(template,level))).get('3',[]),expected)

    def test_separate_weapon_groups_and_no_deceased_dragon_unlock(self):
        self.assertEqual(options(135889,8),[])
        self.assertEqual(options(135889,9),[74088])
        self.assertEqual(options(136120,13),[200150,43820,200149,74092])
        weapon=dict(armor(136186,13),slot=1)
        self.assertNotIn('3',groups(item_body(weapon)))
        self.assertEqual(len(item_body(weapon)),304)

    def test_input_unchanged_other_sockets_and_shared_containers(self):
        item=armor();item['option_groups']={'0':[46610,46608,46608,46606]}
        before=copy.deepcopy(item);body=item_body(item)
        self.assertEqual(item,before)
        self.assertEqual(groups(body),{'0':before['option_groups']['0'],'3':[43510,99266]})
        self.assertIn(body,record(item))
        self.assertIn(body,inventory_restore_map([item]))
        worn=dict(item,group=9,slot=1)
        self.assertIn(item_body(worn),equipment_map([worn]))
        # Group3 remains a server-derived vector; untrusted/stored socket input
        # cannot insert arbitrary effects through the ordinary socket validator.
        with self.assertRaisesRegex(ValueError,'Unsupported option group'):
            item_body(dict(item,option_groups={'3':[43510,99266]}))

    def test_old_save_cold_read_and_level_change_need_no_option_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'save.db';account=LocalAccount(LocalState(path));account.enable_characters()
            with closing(sqlite3.connect(path)) as db:
                with db:
                    db.execute('BEGIN IMMEDIATE')
                    item=grant_items(db,[dict(template=721897,metadata=1,quantity=1,group=1,enhancement=11)])[0]
                before=list(db.iterdump());loaded=next(i for i in load_items(db) if i['uid']==item['uid'])
                self.assertEqual(groups(item_body(loaded))['3'],[43510,99266])
                self.assertNotIn('3',loaded.get('option_groups',{}))
                self.assertEqual(list(db.iterdump()),before)
                for old,new,expected in ((11,10,[43510]),(10,9,[]),(9,-11,[]),(-11,11,[43510,99266])):
                    with db:
                        db.execute('BEGIN IMMEDIATE');replace(db,1001,item['uid'],old,new)
                    loaded=next(i for i in load_items(db) if i['uid']==item['uid'])
                    self.assertEqual(groups(item_body(loaded)).get('3',[]),expected)
            with closing(sqlite3.connect(path)) as db:
                loaded=next(i for i in load_items(db) if i['uid']==item['uid'])
                self.assertEqual(groups(item_body(loaded))['3'],[43510,99266])


    def test_paid_threshold_ack_rollback_and_replay(self):
        from unittest.mock import patch
        from els_server.storage.paid_enhancement import enhance
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'save.db';account=LocalAccount(LocalState(path));account.enable_characters()
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('BEGIN IMMEDIATE')
                item=grant_items(db,[dict(template=118262,metadata=1,quantity=1,group=1,enhancement=9),
                                     dict(template=163135,metadata=2,quantity=3,group=4)])[0]
                db.execute('UPDATE reward_balances SET ed=100000000 WHERE uid=1001')
            payload=struct.pack('>QiiBBBBiB',item['uid'],0,0,0,0,1,0,0,0)
            with closing(sqlite3.connect(path)) as db:before=list(db.iterdump())
            with patch('els_server.storage.paid_enhancement.acknowledgement',side_effect=RuntimeError('encode')):
                with self.assertRaisesRegex(RuntimeError,'encode'):
                    enhance(path,1001,payload,'unlock-rollback',lambda n:0)
            with closing(sqlite3.connect(path)) as db:self.assertEqual(before,list(db.iterdump()))
            answer=enhance(path,1001,payload,'unlock-success',lambda n:0)
            with closing(sqlite3.connect(path)) as db:
                saved=next(i for i in load_items(db) if i['uid']==item['uid']);after=list(db.iterdump())
            self.assertEqual(saved['enhancement'],10)
            self.assertEqual(groups(item_body(saved))['3'],[43510])
            self.assertIn(item_body(saved),answer[0].payload)
            replay=enhance(path,1001,payload,'unlock-success',lambda n:self.fail('Replay redrew enhancement'))
            # Replays use native outcome0 while returning current absolute items.
            self.assertEqual(replay[0].kind,0x600)
            self.assertIn(item_body(saved),replay[0].payload)
            with closing(sqlite3.connect(path)) as db:self.assertEqual(after,list(db.iterdump()))


if __name__=='__main__':unittest.main()
