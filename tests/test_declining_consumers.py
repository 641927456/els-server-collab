"""Unrelated/foreign items must decline before full projections or any write."""
from contextlib import closing,ExitStack
import importlib,json,runpy,sqlite3,struct,tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

class FullProjectionReached(Exception): pass

ROUTES={
    'capacity':('boosting_2026_nested_capacity','use_ticket'),
    'resonance':('resonance_state','use_book'),
    'custom':('character_custom','use_book'),
    'force':('boosting_2026_force_inventory','use_book'),
    'artifact':('artifact_progression','action'),
    'title':('titles','use_item'),
    'expansion':('expansion_items','use_expansion_item'),
    'skill':('skill_unlocks','use_skill_book'),
}

class DecliningConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from els_server.domain.boosting_2026_nested_capacity import register
        register()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'owned.sqlite3'
        self.payload=struct.pack('>QQiiIB',1001001,0,0,0,0,0)
        with closing(sqlite3.connect(self.path))as db,db:
            db.executescript('''
            CREATE TABLE characters(uid INTEGER PRIMARY KEY,name TEXT,unit_type INTEGER,unit_class INTEGER,level INTEGER,transcendence INTEGER,master INTEGER,revision INTEGER);
            INSERT INTO characters VALUES(1001,'OwnedFixture',1,1,99,0,0,0);
            CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER);
            INSERT INTO character_owners VALUES(1001,2);
            CREATE TABLE inventory_items(uid INTEGER PRIMARY KEY,owner INTEGER,template INTEGER,metadata INTEGER,count INTEGER,bag_group INTEGER,slot INTEGER);
            INSERT INTO inventory_items VALUES(1001001,1001,77000,2,1,6,0);
            CREATE TABLE reward_balances(uid INTEGER PRIMARY KEY,ed INTEGER,revision INTEGER);
            INSERT INTO reward_balances VALUES(1001,1000,0);
            ''')

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())

    def call(self,name):
        module,method=ROUTES[name]
        fn=getattr(importlib.import_module('els_server.storage.'+module),method)
        if name in ('resonance','custom','force'):
            return fn(self.path,1001,2,self.payload,'owned-classification')
        if name=='artifact':
            return fn(self.path,1001,'potion',self.payload,'owned-classification',account_id=2)
        return fn(self.path,1001,self.payload,'owned-classification')

    def block_projections(self,stack):
        modules=[importlib.import_module('els_server.storage.inventory_state')]
        modules += [importlib.import_module('els_server.storage.'+v[0])for v in ROUTES.values()]
        for module in modules:
            if hasattr(module,'load_items'):
                stack.enter_context(patch.object(module,'load_items',side_effect=FullProjectionReached('full inventory')))
        from els_server.storage import artifact_progression
        stack.enter_context(patch.object(artifact_progression,'load_character',side_effect=FullProjectionReached('full character')))

    def decline(self,name):
        for owner in (1001,1002):
            with self.subTest(name=name,source_owner=owner):
                with closing(sqlite3.connect(self.path))as db,db:
                    db.execute('UPDATE inventory_items SET owner=?',(owner,))
                before=self.dump()
                with ExitStack()as stack:
                    self.block_projections(stack)
                    self.assertIsNone(self.call(name))
                self.assertEqual(self.dump(),before)

    def matched(self,name):
        module=importlib.import_module('els_server.storage.'+ROUTES[name][0])
        if name=='capacity':template=next(iter(module.items()))
        elif name=='resonance':template=next(iter(module.book_templates()))
        elif name in ('custom','force'):template=next(iter(module.catalog()))
        elif name=='artifact':template=next(iter(module.rules.catalog()['level_up_items']))
        elif name=='title':template=int(next(iter(module.catalog()['items'])))
        elif name=='expansion':template=module.ORDINARY_COUPON
        else:
            from els_server.domain.skill_unlocks import catalog
            template=int(next(iter(catalog()['books'])))
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE inventory_items SET template=?',(template,))
        before=self.dump()
        with ExitStack()as stack:
            self.block_projections(stack)
            with self.assertRaises(FullProjectionReached):self.call(name)
        self.assertEqual(self.dump(),before)

    def test_pet_support_unrelated_item_never_enters_writer_or_inventory_projection(self):
        from els_server.domain.pet_support_flow import handle
        from els_server.protocol.protocol_codec import Event
        session=SimpleNamespace(client_build='dx11_260923',item_test=True,role='game',phase='town_ready',
            shop_session_id='owned-probe',account=SimpleNamespace(uid=1001,store=SimpleNamespace(path=self.path),
                get_inventory_snapshot=lambda:(_ for _ in ()).throw(FullProjectionReached('full snapshot'))))
        before=self.dump()
        with patch('els_server.storage.pet_support.handle',side_effect=FullProjectionReached('pet writer')):
            self.assertIsNone(handle(session,Event(0x202,kind=0x219,payload=self.payload),1))
        self.assertEqual(self.dump(),before)

    def test_pet_support_consumed_receipt_still_reaches_original_replay(self):
        from els_server.domain.pet_support_flow import handle
        from els_server.protocol.protocol_codec import Event
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('DELETE FROM inventory_items')
            db.execute('CREATE TABLE pet_support_receipts(owner INTEGER,operation TEXT,context TEXT)')
            db.execute('INSERT INTO pet_support_receipts VALUES(?,?,?)',(1001,'owned-probe:pet:1',json.dumps(dict(kind=0x219,pet=0))))
        session=SimpleNamespace(client_build='dx11_260923',item_test=True,role='game',phase='town_ready',
            shop_session_id='owned-probe',account=SimpleNamespace(uid=1001,store=SimpleNamespace(path=self.path),
                get_inventory_snapshot=lambda:{'items':[]}))
        expected=[Event(0x201,kind=0x21a,payload=bytes(36))]
        with patch('els_server.storage.pet_support.handle',return_value=expected)as original:
            self.assertEqual(handle(session,Event(0x202,kind=0x219,payload=self.payload),1),expected)
            original.assert_called_once()

    def test_town_dialogue_without_supported_task_skips_full_character(self):
        from els_server.storage.town_dialogue import interact
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('CREATE TABLE character_quests(owner INTEGER,quest INTEGER)')
        store=SimpleNamespace(path=self.path,uid=1001,account_id=2)
        with patch('els_server.storage.town_dialogue.catalog',return_value={'npc_bindings':{'10018':{}},'quests':{}}), \
             patch('els_server.storage.account_contract26780_scope.has_active',return_value=False), \
             patch('els_server.storage.town_dialogue.load_character',side_effect=FullProjectionReached('dialogue role')):
            self.assertIsNone(interact(store,10018,'owned-dialogue'))

    def test_town_dialogue_supported_task_retains_full_character_checks(self):
        from els_server.storage.town_dialogue import interact
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('CREATE TABLE character_quests(owner INTEGER,quest INTEGER)')
            db.execute('INSERT INTO character_quests VALUES(1001,13)')
        store=SimpleNamespace(path=self.path,uid=1001,account_id=2)
        with patch('els_server.storage.town_dialogue.catalog',return_value={'npc_bindings':{'10018':{}},'quests':{'13':{}}}), \
             patch('els_server.storage.town_dialogue.load_character',side_effect=FullProjectionReached('dialogue role')):
            with self.assertRaises(FullProjectionReached):interact(store,10018,'owned-dialogue')

    def test_limited_pet_declines_other_pet_source_before_full_inventory(self):
        # activate lazily imports this module; load it before replacing the
        # inventory reader so the test stub cannot become a persistent alias.
        from els_server.storage import companion_state
        from els_server.storage.boosting_2026_limited_pet import activate
        from els_server.protocol.local_messages import wstring
        payload=struct.pack('>Q',1001001)+wstring('OwnedPet')
        with patch('els_server.storage.boosting_2026_limited_pet.enabled',return_value=True), \
             patch('els_server.storage.inventory_state.load_items',side_effect=FullProjectionReached('pet bag')):
            self.assertIsNone(activate(self.path,1001,payload,'owned-pet',account_id=2))


def decline_case(name):
    def test(self):self.decline(name)
    return test
def matched_case(name):
    def test(self):self.matched(name)
    return test
for name in ROUTES:
    setattr(DecliningConsumerTests,'test_declines_unrelated_'+name,decline_case(name))
    setattr(DecliningConsumerTests,'test_matching_'+name+'_retains_original_full_validation',matched_case(name))

class ExistingPetBusinessTests(unittest.TestCase):
    def test_existing_pet_support_consumption_replay_and_rollback(self):
        runpy.run_path(str(Path(__file__).with_name('test_pet_support.py')),run_name='__main__')

    def test_existing_pet_gesture_and_phase_contract(self):
        runpy.run_path(str(Path(__file__).with_name('test_pet_actions.py')),run_name='__main__')

class TitleBusinessTests(unittest.TestCase):
    def test_title_consume_rollback_spent_source_replay_and_cold_ownership(self):
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        from els_server.storage.inventory_state import grant_items,load_items
        from els_server.storage.titles import use_item,state,TitleUseError
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)as folder:
            path=Path(folder)/'title.sqlite3'
            account=LocalAccount(LocalState(path));account.enable_characters()
            with closing(sqlite3.connect(path))as db,db:
                item=grant_items(db,[dict(template=293029,metadata=0,group=4,quantity=1)])[0]
                before=list(db.iterdump())
            payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
            with patch('els_server.storage.titles.wire.initialization',side_effect=ValueError('encoding failed')):
                with self.assertRaises(ValueError):use_item(path,1001,payload,'title-once')
            with closing(sqlite3.connect(path))as db:
                self.assertEqual(list(db.iterdump()),before)
            self.assertFalse(use_item(path,1001,payload,'title-once')['replayed'])
            with closing(sqlite3.connect(path))as db:
                committed=list(db.iterdump());self.assertEqual(load_items(db,1001),[])
            self.assertTrue(use_item(path,1001,payload,'title-once')['replayed'])
            with closing(sqlite3.connect(path))as db:
                self.assertEqual(list(db.iterdump()),committed)
            self.assertIn(12010,{r['title']for r in state(path,1001)['owned']})
            with closing(sqlite3.connect(path))as db,db:
                replacement=grant_items(db,[dict(template=293029,metadata=0,group=4,quantity=1)])[0]
            with self.assertRaises(TitleUseError)as error:
                use_item(path,1001,struct.pack('>QQiiIB',replacement['uid'],0,0,0,0,0),'duplicate-title')
            self.assertEqual(error.exception.result,499)
            with closing(sqlite3.connect(path))as db:
                self.assertEqual(load_items(db,1001)[0]['count'],1)

if __name__=='__main__':unittest.main()
