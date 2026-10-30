"""Pet automatic-consume slots: MP restorers are not only the fixed kind.

Two separate defects made the auto-consume dialog unusable:

* the MP slot accepted effect kind 2 only, while the HP slot accepted both its
  fixed (1) and proportional (13) forms. domain/consumables.py documents kind 19
  as the proportional MP recovery ('HP kind13 100%, MP kind19 100%'), so a pet
  whose owner holds only a kind-19 MP potion could never fill the MP slot.
* every rejection answered 0x8a2 with the DEFAULT map, which tells the client
  both slots are empty. The saved bindings were intact in the database, but the
  dialog blanked out and the dragged bottle disappeared, so a refusal looked
  like the slot being unusable rather than the item being ineligible.
"""
import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path

from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.quick_bindings import item_binding
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event
from els_server.storage.companion_state import handle as companion,snapshot
from els_server.storage.consumables import use
from els_server.storage.inventory_state import grant_items
from els_server.storage.local_state import LocalState
from els_server.storage.pet_support import automatic,handle as pet

HP_POTION=77000      # effect kind 1
FIXED_MP=77010       # effect kind 2
PERCENT_HP=79063     # effect kind 13
PERCENT_MP=79064     # effect kind 19


def bindings(hp,mp):return struct.pack('>iIiiii',2,2,0,hp,1,mp)
def pet_use(item,active=0):return struct.pack('>QQiiIB',item,active,0,0,0,0)
def parse(ack):
    # 0x8a2 is result:int, count:int, then binding_map = count:int, (key,value) x2.
    result,count=struct.unpack_from('>ii',ack.payload,0)
    return result,struct.unpack_from('>i',ack.payload,16)[0],struct.unpack_from('>i',ack.payload,24)[0],count


class PetAutomaticBindingTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'bindings.sqlite3'
        self.account=LocalAccount(LocalState(self.path))
        self.account.enable_characters();self.account.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path)) as db,db:
            rows=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=2)
                  for t in (550427,500720,164566,HP_POTION,FIXED_MP,PERCENT_HP,PERCENT_MP)]
            self.got={i['template']:i for i in grant_items(db,rows)}
        egg=self.got[550427]
        companion(self.path,1001,0x2e8,struct.pack('>Q',egg['uid'])+wstring('Auto'),'Auto')
        self.active=snapshot(self.path,1001)['companions'][0]['uid']
        pet(self.path,1001,0x219,pet_use(self.got[500720]['uid'],self.active),'pickup')
        pet(self.path,1001,0x219,pet_use(self.got[164566]['uid'],self.active),'expand')
        companion(self.path,1001,0x2ec,struct.pack('>Q',self.active),'summon')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertTrue(automatic(db,1001)['automatic'])
            self.assertEqual(automatic(db,1001)['upgrade'],0)

    def save(self,hp,mp,operation):
        return pet(self.path,1001,0x8a1,bindings(item_binding(hp) if hp else 0,
                                                  item_binding(mp) if mp else 0),operation)

    def saved(self):
        with closing(sqlite3.connect(self.path)) as db:state=automatic(db,1001)
        return state['hp_binding'],state['mp_binding']

    def test_proportional_mp_potion_fills_the_mp_slot(self):
        result,hp,mp,count=parse(self.save(HP_POTION,PERCENT_MP,'percent-mp')[0])
        self.assertEqual((result,hp,mp,count),(0,item_binding(HP_POTION),item_binding(PERCENT_MP),2))
        self.assertEqual(self.saved(),(item_binding(HP_POTION),item_binding(PERCENT_MP)))

    def test_fixed_mp_potion_still_fills_the_mp_slot(self):
        self.assertEqual(parse(self.save(HP_POTION,FIXED_MP,'fixed-mp')[0])[:3],
                         (0,item_binding(HP_POTION),item_binding(FIXED_MP)))

    def test_hp_only_potions_still_refuse_the_mp_slot(self):
        for potion in (HP_POTION,PERCENT_HP):
            with self.assertRaises(ValueError) as caught:
                self.save(HP_POTION,potion,'mp-'+str(potion))
            self.assertEqual(str(caught.exception),'Automatic consumable does not restore the selected resource')
        self.assertEqual(self.saved(),(0,0))

    def test_refusal_echoes_the_saved_bindings_instead_of_blanking_the_dialog(self):
        self.save(HP_POTION,PERCENT_MP,'seed')
        before=self.saved()
        with self.assertRaises(ValueError):self.save(HP_POTION,PERCENT_HP,'bad')
        # The session arm answers instead of raising; the saved map must survive.
        session=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                             npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                             reward_test=True,item_test=True)
        session.role='game';session.phase='town_ready'
        reply=session.handle(Event(0x202,kind=0x8a1,payload=bindings(before[0],item_binding(PERCENT_HP))),901)
        result,hp,mp,count=parse(reply[0])
        self.assertEqual((result,count),(-1,2))
        self.assertEqual((hp,mp),before)
        self.assertEqual(self.saved(),before)

    def test_the_bound_proportional_potion_is_actually_drunk_from_the_mp_slot(self):
        self.save(HP_POTION,PERCENT_MP,'seed')
        answer=use(self.path,1001,struct.pack('>HBBB',1,0,0,0),'drink-mp',now=5000,automatic_use=True)
        self.assertEqual([e.kind for e in answer],[0x65f,0x115])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count FROM inventory_items WHERE owner=1001 AND template=?',
                                        (PERCENT_MP,)).fetchone()[0],1)


if __name__=='__main__':
    unittest.main()
