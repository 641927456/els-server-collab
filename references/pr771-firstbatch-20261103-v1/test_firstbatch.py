"""Current-parent first-batch business checks using disposable owned saves."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch

from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.quick_bindings import item_binding
from els_server.domain.consumables import require_usable
from els_server.domain.pet_support import PRODUCTS,offers,variant_definitions
from els_server.domain.pet_support_flow import handle as pet_flow
from els_server.domain.consumable_flow import handle as consumable_flow
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.quick_slots import empty,encode,save_request
from els_server.storage.consumables import use
from els_server.storage.companion_state import handle as companion,snapshot
from els_server.storage import pet_support as pet
from els_server.storage import pet_support_periods as periods

NEW_ITEMS=(135402,78982,78360,78370,78380,78390,78400,78410,712040,712041)
PICKUP=(161117,301579,100000120,100003044)
ALIASES=(*PICKUP,720856,720849)
NOW=1793630000

def ticket(item,pet=0):return struct.pack('>QQiiIB',item,pet,0,0,0,0)
def drink(slot=0):return struct.pack('>HBBB',slot,0,0,0)
def bindings(hp,mp):return struct.pack('>iIiiii',2,2,0,hp,1,mp)

class FirstBatch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='firstbatch-',dir=Path(__file__).parent/'tmp')
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'own.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.account.get_inventory_snapshot()

    def grant(self,*pairs):
        with closing(sqlite3.connect(self.path))as db,db:
            return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],
                group=TEMPLATE_BAG_GROUPS[t],quantity=n)for t,n in pairs])

    def count(self,template):
        with closing(sqlite3.connect(self.path))as db:
            return db.execute('SELECT coalesce(sum(count),0)FROM inventory_items WHERE owner=1001 AND template=?',(template,)).fetchone()[0]

    def state(self):
        with closing(sqlite3.connect(self.path))as db:return pet.automatic(db,1001)

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())

    def pet(self):
        egg=self.grant((550427,1))[0]
        companion(self.path,1001,0x2e8,struct.pack('>Q',egg['uid'])+wstring('BatchPet'),'first-pet')
        return snapshot(self.path,1001)['companions'][0]['uid']

    def session(self,phase='town_ready'):
        s=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
            npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        s.role='game';s.phase=phase;s.dungeon_substage_synced=phase=='dungeon_active'
        return s

    def bind_shortcut(self,template):
        save_request(self.path,struct.pack('>i',1)+encode({**empty(),0:item_binding(template)}))

    def unlock(self):
        active=self.pet();items=self.grant((720856,1),(720849,1))
        for index,item in enumerate(items):
            pet.handle(self.path,1001,0x219,ticket(item['uid']),'unlock-'+str(index),now=NOW)
        return active

    def test_all_ten_consume_once_and_cold_read_without_changing_native_cooldowns(self):
        self.grant(*[(t,2)for t in NEW_ITEMS])
        for index,t in enumerate(NEW_ITEMS):
            with self.subTest(template=t):
                self.bind_shortcut(t);when=NOW+61*index
                replies=use(self.path,1001,drink(),'use-'+str(t),now=when,allow_apples=True,account_id=1)
                self.assertEqual([e.kind for e in replies],[0x114,0x115])
                self.assertEqual(struct.unpack('>Qi?Q?',replies[1].payload),(1001,t,False,0,False))
                self.assertEqual(self.count(t),1)
                self.assertEqual(len(use(self.path,1001,drink(),'use-'+str(t),now=when+1,allow_apples=True,account_id=1)),1)
                self.assertEqual(self.count(t),1)
                meta=require_usable(t,1)
                self.assertEqual(meta['cooldown_seconds'],30)
                with closing(sqlite3.connect(self.path))as db:
                    ready=db.execute('SELECT ready_at FROM consumable_cooldowns WHERE owner=1001 AND cooldown_group=?',(meta['cooldown_group'],)).fetchone()[0]
                self.assertEqual(ready,when+30)
                # Exhaust this source before testing another template sharing
                # its native binding; the shortcut chooses an instance, not ID.
                use(self.path,1001,drink(),'finish-'+str(t),now=when+30,allow_apples=True,account_id=1)
                self.assertEqual(self.count(t),0)
        cold=LocalAccount(LocalState(self.path));cold.enable_characters()
        current={i['template']:i['count']for i in cold.get_inventory_snapshot()['items']}
        self.assertFalse(set(NEW_ITEMS)&current.keys())

    def test_consumable_rejection_and_encoding_failure_have_no_write(self):
        self.grant((78360,2));self.bind_shortcut(78360);before=self.dump()
        with self.assertRaises(ValueError):use(self.path,1001,drink(),'foreign-account',now=NOW,allow_apples=True,account_id=2)
        with self.assertRaises(ValueError):use(self.path,1001,drink(),'unloaded',now=NOW,allow_apples=False,account_id=1)
        with patch('els_server.storage.consumables.encode_event',side_effect=ValueError('encode failure')):
            with self.assertRaises(ValueError):use(self.path,1001,drink(),'encode',now=NOW,allow_apples=True,account_id=1)
        self.assertEqual(self.dump(),before)

    def test_ball_aliases_choose_eligible_instance_and_share_native_timer(self):
        self.grant((78370,2),(712040,2));self.bind_shortcut(78370)
        use(self.path,1001,drink(),'water',now=NOW,allow_apples=True,account_id=1)
        self.assertEqual((self.count(78370),self.count(712040)),(1,2))
        with self.assertRaises(ValueError):use(self.path,1001,drink(),'cooling',now=NOW+1,allow_apples=True,account_id=1)
        self.assertEqual((self.count(78370),self.count(712040)),(1,2))

    def test_consumable_session_dispatch_and_stage_gate(self):
        self.grant((135402,2));self.bind_shortcut(135402);s=self.session()
        e=Event(0x202,kind=0x113,payload=drink(),performers=(0,))
        self.assertEqual(struct.unpack_from('>i',consumable_flow(s,e,1)[0].payload)[0],-1)
        self.assertEqual(self.count(135402),2)
        s.phase='dungeon_active';s.dungeon_substage_synced=True
        replies=consumable_flow(s,e,2)
        self.assertEqual([r.kind for r in replies],[0x114,0x115]);self.assertEqual(self.count(135402),1)

    def test_permanent_aliases_keep_original_products_and_no_new_shop_offers(self):
        self.assertEqual({r['template']for r in variant_definitions()},set(ALIASES))
        self.assertTrue({500720,164566,330562,300640,300643,300644,500867}<=PRODUCTS.keys())
        self.assertFalse(set(ALIASES)&{r['template']for r in offers()})
        self.assertEqual(set(periods.PRODUCTS),{300640,300643,300644,500867})

    def test_each_pickup_alias_consumes_one_and_does_not_repeat(self):
        active=self.pet();items=self.grant(*[(t,2)for t in PICKUP])
        for item in items:
            t=item['template']
            with self.subTest(template=t):
                with closing(sqlite3.connect(self.path))as db,db:
                    pet.ensure(db)
                    db.execute('DELETE FROM pet_entitlements WHERE pet=?',(active,))
                replies=pet.handle(self.path,1001,0x219,ticket(item['uid'],active),'pickup-'+str(t),now=NOW)
                self.assertEqual([e.kind for e in replies],[0x21a,0x2fc]);self.assertEqual(self.count(t),1)
                pet.handle(self.path,1001,0x219,ticket(item['uid'],active),'pickup-'+str(t),now=NOW+1)
                self.assertEqual(self.count(t),1)
                with self.assertRaises(ValueError):pet.handle(self.path,1001,0x219,ticket(item['uid'],active),'second-'+str(t),now=NOW+2)
                self.assertEqual(self.count(t),1)

    def test_upgrade_requires_expansion_and_replay_preserves_entitlements(self):
        self.pet();items=self.grant((720856,2),(720849,2));expand,upgrade=items
        before=self.dump()
        with self.assertRaises(ValueError):pet.handle(self.path,1001,0x219,ticket(upgrade['uid']),'early',now=NOW)
        self.assertEqual(self.dump(),before)
        pet.handle(self.path,1001,0x219,ticket(expand['uid']),'expand',now=NOW)
        pet.handle(self.path,1001,0x219,ticket(upgrade['uid']),'upgrade',now=NOW)
        pet.handle(self.path,1001,0x219,ticket(upgrade['uid']),'upgrade',now=NOW+1)
        self.assertEqual((self.state()['automatic'],self.state()['upgrade']),(1,1))
        self.assertEqual((self.count(720856),self.count(720849)),(1,1))
        cold=LocalAccount(LocalState(self.path));cold.enable_characters()
        with closing(sqlite3.connect(cold.store.path))as db:self.assertEqual(pet.automatic(db,1001)['upgrade'],1)

    def test_pet_alias_encode_and_authority_failure_rollback(self):
        active=self.pet();item=self.grant((161117,2))[0];before=self.dump()
        with patch('els_server.storage.pet_support.encode_event',side_effect=ValueError('encode failure')):
            with self.assertRaises(ValueError):pet.handle(self.path,1001,0x219,ticket(item['uid'],active),'encode',now=NOW)
        self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):pet.handle(self.path,1001,0x219,ticket(item['uid'],active),'foreign',now=NOW,account_id=2)
        checks=[]
        def change_before_commit(db):
            checks.append(1)
            if len(checks)==2:raise ValueError('actor changed')
        with self.assertRaises(ValueError):pet.handle(self.path,1001,0x219,ticket(item['uid'],active),'changed',now=NOW,account_id=1,prepare=change_before_commit)
        self.assertEqual(self.dump(),before)

    def test_concurrent_coupon_replay_deducts_only_one(self):
        active=self.pet();item=self.grant((161117,2))[0]
        def attempt(_):return pet.handle(self.path,1001,0x219,ticket(item['uid'],active),'same',now=NOW)
        with ThreadPoolExecutor(max_workers=2)as pool:answers=list(pool.map(attempt,range(2)))
        self.assertEqual(len(answers),2);self.assertEqual(self.count(161117),1)

    def test_existing_timed_pickup_and_automatic_keep_expiry_and_replay(self):
        active=self.pet()
        # These are retained owned-only tickets: do not reopen their disabled
        # generic acquisition merely to construct a disposable historical save.
        items=[]
        with closing(sqlite3.connect(self.path))as db,db:
            for index,t in enumerate((300643,300640)):
                for instance in range(2):
                    slot=db.execute('SELECT coalesce(max(slot),-1)+1 FROM inventory_items WHERE owner=1001 AND bag_group=4').fetchone()[0]
                    uid=900000001+index*2+instance
                    db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(uid,1001,t,VERIFIED_TEMPLATES[t],1,4,slot))
                    items.append(dict(uid=uid,template=t))
        for t,target,kind in ((300643,active,'pickup'),(300640,0,'automatic')):
            item=next(i for i in items if i['template']==t);payload=ticket(item['uid'],target)
            pet.handle(self.path,1001,0x219,payload,'timed-'+str(t),now=NOW,account_id=1,prepare=lambda db:None)
            pet.handle(self.path,1001,0x219,payload,'timed-'+str(t),now=NOW+60,account_id=1,prepare=lambda db:None)
            self.assertEqual(self.count(t),1)
            with closing(sqlite3.connect(self.path))as db:deadline=periods.period(db,1001,kind,target)
            self.assertEqual(deadline,NOW+15*86400)
        with closing(sqlite3.connect(self.path))as db:
            self.assertFalse(pet.automatic(db,1001,now=NOW+15*86400+1)['automatic'])
        permanent=self.grant((720856,1))[0]
        pet.handle(self.path,1001,0x219,ticket(permanent['uid']),'permanent',now=NOW+61)
        with closing(sqlite3.connect(self.path))as db:self.assertIsNone(periods.period(db,1001,'automatic',0))

    def test_percent_mp_binding_is_saved_and_refused_binding_echoes_it(self):
        self.unlock();self.grant((710000,3),(77000,3));s=self.session()
        hp=item_binding(77000);mp=item_binding(710000)
        good=Event(0x202,kind=0x8a1,payload=bindings(hp,mp),performers=(0,))
        reply=pet_flow(s,good,101)
        self.assertEqual(struct.unpack('>iiIiiii',reply[0].payload),(0,2,2,0,hp,1,mp))
        bad=Event(0x202,kind=0x8a1,payload=bindings(hp,123456789),performers=(0,))
        before=self.dump();reply=pet_flow(s,bad,102)
        self.assertEqual(struct.unpack('>iiIiiii',reply[0].payload),(-1,2,2,0,hp,1,mp))
        self.assertEqual(self.dump(),before)

    def test_refused_coupon_and_settings_echo_current_saved_settings(self):
        self.unlock();coupon=self.grant((720856,2))[0];s=self.session()
        reply=pet_flow(s,Event(0x202,kind=0x219,payload=ticket(coupon['uid']),performers=(0,)),201)
        self.assertEqual([r.kind for r in reply],[0x21a,0xb3b]);self.assertEqual(self.count(720856),2)
        self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],-1)
        automatic,expiry,hp,mp,upgrade,enabled=struct.unpack_from('>BQBBBB',reply[1].payload)
        self.assertEqual((automatic,hp,mp,upgrade,enabled),(1,50,50,1,1));self.assertGreater(expiry,NOW)
        reply=pet_flow(s,Event(0x202,kind=0x661,payload=b'bad',performers=(0,)),202)
        self.assertEqual(struct.unpack_from('>BQBBBB',reply[0].payload)[0],1)

    def test_pet_session_refuses_foreign_envelope_and_stale_lease_without_writes(self):
        self.unlock();s=self.session();before=self.dump()
        bad=Event(0x202,kind=0x8a1,payload=bindings(0,0),performers=(9,))
        self.assertEqual(struct.unpack_from('>i',pet_flow(s,bad,301)[0].payload)[0],-1)
        good=Event(0x202,kind=0x8a1,payload=bindings(0,0),performers=(0,))
        with patch('els_server.domain.equipment_chip_flow.current_lease',return_value=False):
            self.assertEqual(struct.unpack_from('>i',pet_flow(s,good,302)[0].payload)[0],-1)
        self.assertEqual(self.dump(),before)

    def test_manual_and_automatic_keep_the_original_shared_recovery_cooldown(self):
        active=self.unlock();self.grant((710000,5))
        pet.handle(self.path,1001,0x8a1,bindings(0,item_binding(710000)),'bind-mp')
        companion(self.path,1001,0x2ec,struct.pack('>Q',active),'summon-pet')
        self.bind_shortcut(710000)
        use(self.path,1001,drink(),'manual',now=NOW)
        with self.assertRaises(ValueError):use(self.path,1001,drink(1),'auto-blocked',now=NOW+1,automatic_use=True)
        self.assertEqual(self.count(710000),4)
        use(self.path,1001,drink(1),'auto',now=NOW+30,automatic_use=True)
        with self.assertRaises(ValueError):use(self.path,1001,drink(),'manual-blocked',now=NOW+31)
        self.assertEqual(self.count(710000),3)


if __name__=='__main__':
    (Path(__file__).parent/'tmp').mkdir(exist_ok=True)
    unittest.main(verbosity=2)
