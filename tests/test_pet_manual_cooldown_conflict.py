"""Pet automatic and manual presses commit one shared recovery-group ledger.

The sharing itself is the admitted behavior: tests/test_pet_support.py pins that
a second automatic use inside the window is refused, and the pet gear modifier
m_fReduceRecoveryItemCooltime shortens that same group, which only makes sense
if it is one resource. The gap was reporting. Whichever side lost the race got a
bare result=-1 with the trailing cooldown float left at -1, so the player's
press looked dead and the pet kept re-requesting. These tests pin that the wait
the server reports is the wait it enforces.
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


def request(slot=0):return struct.pack('>HBBB',slot,0,0,0)
def pet_use(item,active=0):return struct.pack('>QQiiIB',item,active,0,0,0,0)
def settings(hp=100,mp=100,hp_seconds=0,mp_seconds=0,enabled=1):
    return struct.pack('>QBBbiiBBB',0,hp,mp,enabled,hp_seconds,mp_seconds,40,0,0)
def result_of(ack):return struct.unpack_from('>i',ack.payload,0)[0]
def cooldown_of(ack):
    # 0x114/0x65f tail is template:int, flag:bool, cooldown:float, slot:uint16.
    return struct.unpack_from('>f',ack.payload,len(ack.payload)-6)[0]


class PetManualCooldownConflictTests(unittest.TestCase):
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

    def ready_at(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT ready_at FROM consumable_cooldowns WHERE owner=1001 AND cooldown_group=?',
                              (GROUP,)).fetchone()[0]

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

    def test_manual_press_locks_the_pet_out_for_exactly_the_reported_wait(self):
        use(self.path,1001,request(),'manual',now=1000)
        deadline=self.ready_at()
        self.assertGreater(deadline-1000,0)
        with self.assertRaises(ConsumableCoolingDown) as caught:
            use(self.path,1001,request(),'auto-early',now=deadline-1,automatic_use=True)
        self.assertAlmostEqual(caught.exception.remaining,1.0)
        self.assertEqual(caught.exception.slot,0)
        self.assertEqual([e.kind for e in use(self.path,1001,request(),'auto-ready',now=deadline,automatic_use=True)],
                         [0x65f,0x115])

    def test_pet_drink_locks_the_manual_press_out_for_exactly_the_reported_wait(self):
        use(self.path,1001,request(),'auto',now=1000,automatic_use=True)
        deadline=self.ready_at()
        with self.assertRaises(ConsumableCoolingDown) as caught:
            use(self.path,1001,request(),'manual-early',now=deadline-0.5)
        self.assertAlmostEqual(caught.exception.remaining,0.5)
        self.assertEqual([e.kind for e in use(self.path,1001,request(),'manual-ready',now=deadline)],[0x114,0x115])

    def test_refusal_answers_on_the_wire_with_the_remaining_seconds(self):
        session=self.session()
        use(self.path,1001,request(),'manual',now=1000)
        with patch('els_server.storage.consumables.time.time',return_value=1010):
            answered=session.handle(Event(0x202,kind=0x65e,payload=request()),801)
        self.assertEqual([e.kind for e in answered],[0x65f])
        self.assertEqual(result_of(answered[0]),-1)
        self.assertAlmostEqual(cooldown_of(answered[0]),self.ready_at()-1010)
        self.assertEqual(self.count(),4)
        before=self.dump()
        with patch('els_server.storage.consumables.time.time',return_value=1010):
            session.handle(Event(0x202,kind=0x65e,payload=request()),802)
        self.assertEqual(self.dump(),before)

    def test_a_real_failure_still_reports_no_invented_wait(self):
        session=self.session()
        use(self.path,1001,request(),'auto',now=1000,automatic_use=True)
        with patch('els_server.storage.consumables.time.time',return_value=1005):
            answered=session.handle(Event(0x202,kind=0x113,payload=request(5)),803)
        self.assertEqual([e.kind for e in answered],[0x114])
        self.assertEqual(result_of(answered[0]),-1)
        self.assertEqual(cooldown_of(answered[0]),-1.0)


if __name__=='__main__':
    unittest.main()
