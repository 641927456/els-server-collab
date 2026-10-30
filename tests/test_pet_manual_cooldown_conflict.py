"""Pet automatic and manual presses now own separate cooldown ledgers.

The pet keeps `pet_auto_cooldowns` (per slot, configured interval floored by the
item's native cooldown and the pet's recovery modifier); the player's manual
press keeps `consumable_cooldowns`. Either side may therefore drink while the
other is cooling, and both still report the wait they actually enforce.
"""
import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from els_server.domain.consumables import ConsumableCoolingDown,require_usable
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.quick_bindings import item_binding
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event
from els_server.storage.companion_state import handle as companion,snapshot
from els_server.storage.consumables import use
from els_server.storage.inventory_state import grant_items
from els_server.storage.local_state import LocalState
from els_server.storage.pet_support import handle as pet
from els_server.storage.quick_slots import empty,encode,save_request

POTION=77000
GROUP=require_usable(POTION,1)['cooldown_group']
SECONDS=require_usable(POTION,1)['cooldown_seconds']


def request(slot=0):return struct.pack('>HBBB',slot,0,0,0)
def pet_use(item,active=0):return struct.pack('>QQiiIB',item,active,0,0,0,0)
def settings(hp=100,mp=100,hp_seconds=0,mp_seconds=0,enabled=1):
    return struct.pack('>QBBbiiBBB',0,hp,mp,enabled,hp_seconds,mp_seconds,40,0,0)
def result_of(ack):return struct.unpack_from('>i',ack.payload,0)[0]
def cooldown_of(ack):
    # 0x114/0x65f tail is template:int, flag:bool, cooldown:float, slot:uint16.
    return struct.unpack_from('>f',ack.payload,len(ack.payload)-6)[0]


class PetManualCooldownIndependenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'conflict.sqlite3'
        self.account=LocalAccount(LocalState(self.path))
        self.account.enable_characters();self.account.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path)) as db,db:
            rows=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=q)
                  for t,q in ((550427,1),(500720,1),(164566,1),(330562,1),(POTION,5))]
            self.got={i['template']:i for i in grant_items(db,rows)}
        egg=self.got[550427]
        companion(self.path,1001,0x2e8,struct.pack('>Q',egg['uid'])+wstring('Auto'),'Auto')
        active=snapshot(self.path,1001)['companions'][0]['uid']
        for step,template in (('pickup',500720),('expand',164566),('upgrade',330562)):
            pet(self.path,1001,0x219,pet_use(self.got[template]['uid'],active),step)
        pet(self.path,1001,0x661,settings(),'settings')
        pet(self.path,1001,0x8a1,struct.pack('>iIiiii',2,2,0,item_binding(POTION),1,0),'bindings')
        companion(self.path,1001,0x2ec,struct.pack('>Q',active),'summon')
        save_request(self.path,struct.pack('>i',1)+encode({**empty(),0:item_binding(POTION)}))

    def group_ready(self):
        with closing(sqlite3.connect(self.path)) as db:
            row=db.execute('SELECT ready_at FROM consumable_cooldowns WHERE owner=1001 AND cooldown_group=?',
                           (GROUP,)).fetchone()
        return row[0] if row else None

    def pet_ready(self,slot=0):
        with closing(sqlite3.connect(self.path)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pet_auto_cooldowns'").fetchone():
                return None
            row=db.execute('SELECT ready_at FROM pet_auto_cooldowns WHERE owner=1001 AND slot=?',(slot,)).fetchone()
        return row[0] if row else None

    def count(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT coalesce(sum(count),0) FROM inventory_items WHERE owner=1001 AND template=?',
                              (POTION,)).fetchone()[0]

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def session(self):
        answer=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                            npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                            reward_test=True,item_test=True)
        answer.role='game';answer.phase='dungeon_active';return answer

    def test_manual_press_leaves_the_pet_free(self):
        use(self.path,1001,request(),'manual',now=1000)
        self.assertEqual(self.group_ready(),1000+SECONDS)
        self.assertIsNone(self.pet_ready())
        answered=use(self.path,1001,request(),'auto-independent',now=1001,automatic_use=True)
        self.assertEqual([e.kind for e in answered],[0x65f,0x115])
        self.assertAlmostEqual(cooldown_of(answered[0]),-1.0)
        # The pet tick must not touch the manual ledger.
        self.assertEqual(self.group_ready(),1000+SECONDS)
        self.assertEqual(self.pet_ready(),1001+SECONDS)

    def test_pet_drink_leaves_the_manual_press_free(self):
        use(self.path,1001,request(),'auto',now=1000,automatic_use=True)
        self.assertEqual(self.pet_ready(),1000+SECONDS)
        self.assertIsNone(self.group_ready())
        answered=use(self.path,1001,request(),'manual-independent',now=1001)
        self.assertEqual([e.kind for e in answered],[0x114,0x115])
        self.assertEqual(self.group_ready(),1001+SECONDS)
        self.assertEqual(self.pet_ready(),1000+SECONDS)

    def test_pet_timer_refusal_reports_its_own_remaining_wait(self):
        session=self.session()
        use(self.path,1001,request(),'auto',now=1000,automatic_use=True)
        with patch('els_server.storage.consumables.time.time',return_value=1010):
            answered=session.handle(Event(0x202,kind=0x65e,payload=request()),801)
        self.assertEqual([e.kind for e in answered],[0x65f])
        self.assertEqual(result_of(answered[0]),-1)
        self.assertAlmostEqual(cooldown_of(answered[0]),self.pet_ready()-1010)
        self.assertEqual(self.count(),4)
        before=self.dump()
        with patch('els_server.storage.consumables.time.time',return_value=1010):
            session.handle(Event(0x202,kind=0x65e,payload=request()),802)
        self.assertEqual(self.dump(),before)

    def test_manual_group_refusal_still_reports_its_remaining_wait(self):
        session=self.session()
        use(self.path,1001,request(),'manual',now=1000)
        with patch('els_server.storage.consumables.time.time',return_value=1010):
            answered=session.handle(Event(0x202,kind=0x113,payload=request()),803)
        self.assertEqual([e.kind for e in answered],[0x114])
        self.assertEqual(result_of(answered[0]),-1)
        self.assertAlmostEqual(cooldown_of(answered[0]),self.group_ready()-1010)

    def test_a_real_failure_still_reports_no_invented_wait(self):
        session=self.session()
        use(self.path,1001,request(),'auto',now=1000,automatic_use=True)
        with patch('els_server.storage.consumables.time.time',return_value=1005):
            answered=session.handle(Event(0x202,kind=0x113,payload=request(5)),804)
        self.assertEqual([e.kind for e in answered],[0x114])
        self.assertEqual(result_of(answered[0]),-1)
        self.assertEqual(cooldown_of(answered[0]),-1.0)

    def test_pet_refusal_raises_the_typed_wait(self):
        use(self.path,1001,request(),'auto',now=1000,automatic_use=True)
        with self.assertRaises(ConsumableCoolingDown) as caught:
            use(self.path,1001,request(),'auto-early',now=1029,automatic_use=True)
        self.assertAlmostEqual(caught.exception.remaining,1.0)
        self.assertEqual(caught.exception.slot,0)


if __name__=='__main__':
    unittest.main()
