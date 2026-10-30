"""Rebranded permanent pet tickets share their base template's entitlement.

The client ships the same coupon under different names for the cash-shop
bundles and the Lalurily/Minime pet lines: 161117, 301579, 100000120 and
100003044 are 'pet auto-pickup', 720856 is the auto-consume slot expansion and
720849 is its upgrade. They were dead items because only the three base
templates were registered, so the 0x219 arm rolled back before the entitlement
ledger and answered the bare use_ack(result=-1).

Official semantics are unchanged by this: the entitlements are still the
boolean pet-scoped pickup flag and the one owner-level automatic/upgrade pair,
the upgrade still requires the expansion first, and each use consumes exactly
one ticket. The variants only join the same ledger through their base product.
The static qualification lives in els_server/data/pet_ticket_variants.json;
tickets that need something the server does not model (period expiry, named-pet
binding, treasure boxes) stay refused there.
"""
import json,sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path

from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.pet_support import (PRODUCTS,SHOP_PRODUCTS,offers,
                                           variant_definitions)
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event
from els_server.storage.companion_state import handle as companion,snapshot
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.local_state import LocalState
from els_server.storage.pet_support import automatic,handle as pet

EGG=550427
PICKUP_VARIANTS=(161117,301579,100000120,100003044)
EXPANSION_VARIANT=720856
UPGRADE_VARIANT=720849
EVIDENCE=json.loads((Path(__file__).resolve().parents[1]/'els_server/data/pet_ticket_variants.json').read_text(encoding='utf8'))
PRODUCT=dict((r['template'],r['product']) for r in EVIDENCE['rows'])


def pet_use(item,active=0):return struct.pack('>QQiiIB',item,active,0,0,0,0)


class PetTicketVariantTests(unittest.TestCase):
    def env(self,*templates,pets=2):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        path=Path(tmp.name)/'variants.sqlite3'
        account=LocalAccount(LocalState(path))
        account.enable_characters();account.get_inventory_snapshot()
        with closing(sqlite3.connect(path)) as db,db:
            rows=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=2)
                  for t in templates]
            granted=grant_items(db,rows)
        got={}
        for item in granted:got.setdefault(item['template'],item)
        for name,egg in zip(('First','Second')[:pets],[i for i in granted if i['template']==EGG]):
            companion(path,1001,0x2e8,struct.pack('>Q',egg['uid'])+wstring(name),name)
        owned=snapshot(path,1001)['companions']
        self.assertEqual(len(owned),pets)
        return path,account,got,(owned[0]['uid'] if owned else 0)

    def count(self,path,template):
        with closing(sqlite3.connect(path)) as db:
            return sum(i['count'] for i in load_items(db) if i['template']==template)

    def state(self,path):
        with closing(sqlite3.connect(path)) as db:return automatic(db,1001)

    def test_variants_are_registered_as_special_tickets(self):
        for template,product in PRODUCT.items():
            self.assertEqual(PRODUCTS[template],product)
            self.assertEqual((VERIFIED_TEMPLATES[template],TEMPLATE_BAG_GROUPS[template]),(0,4))
        for template in SHOP_PRODUCTS:self.assertIn(template,PRODUCTS)

    def test_evidence_rows_rederive_from_the_client_records(self):
        self.assertEqual(sorted(e['template'] for e in variant_definitions()),sorted(PRODUCT))
        self.assertEqual([r['template'] for r in offers()],[*SHOP_PRODUCTS,500030])
        self.assertEqual([o['sku'] for o in offers()],
                         [1200000000+t for t in (*SHOP_PRODUCTS,500030)])
        self.assertEqual(len(variant_definitions()),6)

    def test_each_pickup_variant_grants_pickup_and_drinks_one_ticket(self):
        for template in PICKUP_VARIANTS:
            path,account,got,active=self.env(EGG,template)
            ack=pet(path,1001,0x219,pet_use(got[template]['uid'],active),'pickup-'+str(template))
            self.assertEqual([e.kind for e in ack],[0x21a,0x2fc])
            self.assertEqual([p.get('pickup',False) for p in snapshot(path,1001)['companions']],[True,False])
            self.assertEqual(self.count(path,template),1)
            with self.assertRaises(ValueError) as caught:
                pet(path,1001,0x219,pet_use(got[template]['uid'],active),'again-'+str(template))
            self.assertEqual(str(caught.exception),'Pet already has permanent pickup')
            self.assertEqual(self.count(path,template),1)

    def test_the_base_ticket_and_its_rebrand_share_one_ledger(self):
        path,account,got,active=self.env(EGG,164566,330562,EXPANSION_VARIANT,UPGRADE_VARIANT)
        with self.assertRaises(ValueError) as early:
            pet(path,1001,0x219,pet_use(got[UPGRADE_VARIANT]['uid']),'upgrade-first')
        self.assertEqual(str(early.exception),'Automatic slot must be expanded first')
        self.assertEqual(self.state(path)['automatic'],0)
        ack=pet(path,1001,0x219,pet_use(got[EXPANSION_VARIANT]['uid']),'variant-expand')
        self.assertEqual(ack[-1].kind,0xb3b)
        self.assertEqual(self.state(path)['automatic'],1)
        self.assertEqual(self.count(path,EXPANSION_VARIANT),1)
        pet(path,1001,0x219,pet_use(got[330562]['uid']),'base-upgrade')
        self.assertEqual(self.state(path)['upgrade'],1)
        self.assertEqual(self.count(path,330562),1)
        with self.assertRaises(ValueError) as again:
            pet(path,1001,0x219,pet_use(got[EXPANSION_VARIANT]['uid']),'variant-expand-again')
        self.assertEqual(str(again.exception),'Pet automatic entitlement already unlocked')

    def test_the_upgrade_rebrand_works_after_the_base_expansion(self):
        path,account,got,active=self.env(EGG,164566,UPGRADE_VARIANT)
        pet(path,1001,0x219,pet_use(got[164566]['uid']),'base-expand')
        pet(path,1001,0x219,pet_use(got[UPGRADE_VARIANT]['uid']),'variant-upgrade')
        self.assertEqual((self.state(path)['automatic'],self.state(path)['upgrade']),(1,1))
        self.assertEqual(self.count(path,UPGRADE_VARIANT),1)

    def test_activated_pet_is_still_required(self):
        path,account,got,active=self.env(EGG,EXPANSION_VARIANT,pets=0)
        with self.assertRaises(ValueError) as caught:
            pet(path,1001,0x219,pet_use(got[EXPANSION_VARIANT]['uid'],active),'no-pet')
        self.assertEqual(str(caught.exception),'An activated pet is required')
        self.assertEqual(self.state(path)['automatic'],0)
        self.assertEqual(self.count(path,EXPANSION_VARIANT),2)

    def test_a_session_answers_the_variant_ticket_with_a_real_receipt(self):
        path,account,got,active=self.env(EGG,UPGRADE_VARIANT,EXPANSION_VARIANT)
        pet(path,1001,0x219,pet_use(got[EXPANSION_VARIANT]['uid']),'expand')
        session=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                             npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                             reward_test=True,item_test=True)
        session.role='game';session.phase='town_ready'
        reply=session.handle(Event(0x202,kind=0x219,payload=pet_use(got[UPGRADE_VARIANT]['uid'])),901)
        self.assertEqual([e.kind for e in reply],[0x21a,0xb3b])
        self.assertEqual(struct.unpack_from('>i',reply[0].payload,0)[0],0)
        self.assertEqual(self.state(path)['upgrade'],1)

    def test_a_refused_ticket_answers_with_the_unchanged_state(self):
        path,account,got,active=self.env(EGG,164566,330562)
        pet(path,1001,0x219,pet_use(got[164566]['uid']),'expand')
        pet(path,1001,0x219,pet_use(got[330562]['uid']),'upgrade')
        session=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                             npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                             reward_test=True,item_test=True)
        session.role='game';session.phase='town_ready'
        reply=session.handle(Event(0x202,kind=0x219,payload=pet_use(got[164566]['uid'])),902)
        self.assertEqual([e.kind for e in reply],[0x21a,0xb3b])
        self.assertEqual(struct.unpack_from('>i',reply[0].payload,0)[0],-1)
        automatic,expiry,hp,mp,upgrade,enabled=struct.unpack_from('>BQBBBB',reply[1].payload,0)
        self.assertEqual((automatic,upgrade,enabled),(1,1,1))
        self.assertEqual(self.count(path,164566),1)
        self.assertEqual(session._pet_support_rejection['reason'],'Pet automatic entitlement already unlocked')

    def test_a_refused_ticket_is_attributable(self):
        path,account,got,active=self.env(EGG,330562)
        session=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                             npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                             reward_test=True,item_test=True)
        session.role='game';session.phase='town_ready'
        reply=session.handle(Event(0x202,kind=0x219,payload=pet_use(got[330562]['uid'])),903)
        self.assertEqual(struct.unpack_from('>i',reply[0].payload,0)[0],-1)
        self.assertEqual(session._pet_support_rejection,
                         dict(kind=0x219,reason='Automatic slot must be expanded first',
                              item=got[330562]['uid'],pet=0,a=0,b=0,n=0,flag=0))

    def session(self,account):
        session=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                             npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                             reward_test=True,item_test=True)
        session.role='game';session.phase='town_ready'
        return session

    def test_a_stale_pet_uid_in_the_upgrade_request_still_releases_the_dialog(self):
        path,account,got,active=self.env(EGG,164566,330562)
        pet(path,1001,0x219,pet_use(got[164566]['uid']),'expand')
        reply=self.session(account).handle(
            Event(0x202,kind=0x219,payload=pet_use(got[330562]['uid'],active+999)),904)
        self.assertEqual([e.kind for e in reply],[0x21a,0xb3b])
        self.assertEqual(struct.unpack_from('>i',reply[0].payload,0)[0],-1)
        self.assertEqual(self.state(path)['upgrade'],0)
        self.assertEqual(self.count(path,330562),2)

    def test_unsupported_parameters_still_release_the_dialog(self):
        path,account,got,active=self.env(EGG,164566,330562)
        pet(path,1001,0x219,pet_use(got[164566]['uid']),'expand')
        payload=struct.pack('>QQiiIB',got[330562]['uid'],0,1,0,0,0)
        session=self.session(account)
        reply=session.handle(Event(0x202,kind=0x219,payload=payload),905)
        self.assertEqual([e.kind for e in reply],[0x21a,0xb3b])
        self.assertEqual(struct.unpack_from('>i',reply[0].payload,0)[0],-1)
        self.assertEqual(self.state(path)['upgrade'],0)
        self.assertEqual(self.count(path,330562),2)
        self.assertEqual(session._pet_support_rejection['a'],1)

    def test_unknown_item_uses_still_reach_the_generic_families(self):
        path,account,got,active=self.env(EGG,164566)
        session=self.session(account)
        reply=session.handle(Event(0x202,kind=0x219,payload=pet_use(999999999)),906)
        self.assertEqual([e.kind for e in reply],[0x21a])
        self.assertEqual(struct.unpack_from('>i',reply[0].payload,0)[0],-1)
        self.assertEqual(session._pet_support_rejection['reason'],'unhandled item')

    def test_unmodelled_tickets_stay_outside_the_pet_products(self):
        for template in EVIDENCE['excluded']:
            template=int(template)
            self.assertNotIn(template,PRODUCTS)
            self.assertNotIn(template,set(PRODUCT))
            if template!=500867:
                # 500867 is registered as its own item; the others have no body.
                self.assertNotIn(template,VERIFIED_TEMPLATES)
            else:
                path,account,got,active=self.env(EGG,template)
                self.assertIsNone(pet(path,1001,0x219,pet_use(got[template]['uid'],active),'timed'))
                self.assertEqual(self.count(path,template),2)


if __name__=='__main__':
    unittest.main()
