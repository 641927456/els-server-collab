"""Owned temporary saves and original bounded native cooldown consumers."""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,json,sqlite3,struct,sys,tempfile,unittest

OUT=Path(__file__).resolve().parent
ROOT=Path('G:/els')
BASE=Path(json.loads((OUT/'base.json').read_bytes())['path'])
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(BASE/'vendor'),str(ROOT/'tools/pylibs'),str(ROOT/'tools')]
import els_server.domain,els_server.storage
if '--baseline' in sys.argv:
    sys.argv.remove('--baseline')
else:
    for package,part in ((els_server.domain,'domain'),(els_server.storage,'storage')):
        package.__path__.insert(0,str(OUT/'source/els_server'/part))

from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.companion_state import handle as companion,snapshot
from els_server.storage.pet_support import handle as pet
from els_server.storage.consumables import use
from els_server.domain.consumable_flow import handle
from els_server.domain.consumables import ConsumableCoolingDown,recovery_cooldown_seconds
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.quick_bindings import item_binding
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event
from els_server.storage.quick_slots import save_request,empty,encode

def request(slot):return struct.pack('>HBBB',slot,0,0,0)
def tail(ack):return struct.unpack('>i?fH',ack.payload[-11:])
def settings(hp_seconds=0,mp_seconds=0):
    return struct.pack('>QBBbiiBBB',0,100,100,1,hp_seconds,mp_seconds,40,0,0)

class PetCooldownTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='owned-',dir=OUT)
        self.addCleanup(temporary.cleanup)
        self.path=Path(temporary.name)/'game.sqlite3'
        prepare(self.path)
        self.uid=Characters(self.path).create('PetCDTest',1,'owned-create')['uid']
        self.account=LocalAccount(LocalState(self.path,self.uid));self.account.enable_characters()
        self.account.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path)) as db,db:
            items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],
                group=TEMPLATE_BAG_GROUPS[t],quantity=n) for t,n in
                ((550427,1),(164566,1),(330562,1),(77000,8),(77010,8))],self.uid)
        got={i['template']:i for i in items}
        companion(self.path,self.uid,0x2e8,struct.pack('>Q',got[550427]['uid'])+wstring('CDPet'),'activate')
        active=snapshot(self.path,self.uid)['companions'][0]['uid']
        for template in (164566,330562):
            pet(self.path,self.uid,0x219,struct.pack('>QQiiIB',got[template]['uid'],0,0,0,0,0),str(template))
        pet(self.path,self.uid,0x661,settings(),'settings')
        pet(self.path,self.uid,0x8a1,struct.pack('>iIiiii',2,2,0,item_binding(77000),1,item_binding(77010)),'bind')
        companion(self.path,self.uid,0x2ec,struct.pack('>Q',active),'summon')
        self.session=SimpleNamespace(role='game',phase='dungeon_active',account=self.account,shop_session_id='owned-cd',dungeon_substage_synced=False)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def count(self,template):
        with closing(sqlite3.connect(self.path)) as db:
            return sum(i['count'] for i in load_items(db,self.uid) if i['template']==template)

    def test_success_transmits_the_enforced_native_cooldown_for_both_slots(self):
        with patch('els_server.storage.pet_support.active_effects',return_value={'m_fReduceRecoveryItemCooltime':.055}):
            for slot,template in ((0,77000),(1,77010)):
                with self.subTest(slot=slot):
                    answer=use(self.path,self.uid,request(slot),'success-'+str(slot),now=1000,automatic_use=True)
                    self.assertEqual([e.kind for e in answer],[0x65f,0x115])
                    self.assertEqual(tail(answer[0]),(template,False,29.,slot))
                    self.assertEqual(self.count(template),7)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT ready_at FROM pet_consumable_cooldowns ORDER BY cooldown_group').fetchall(),[(1029.,),(1029.,)])

    def test_cooling_mp_replies_to_mp_without_debit_or_effect(self):
        use(self.path,self.uid,request(1),'mp-first',now=1000,automatic_use=True)
        before=self.dump()
        with patch('els_server.storage.consumables.time.time',return_value=self.uid):
            for sequence in range(10,15):
                answer=handle(self.session,Event(0x202,kind=0x65e,payload=request(1)),sequence)
                self.assertEqual([e.kind for e in answer],[0x65f])
                self.assertEqual(struct.unpack_from('>i',answer[0].payload)[0],1369)
                self.assertEqual(tail(answer[0])[-1],1)
        self.assertEqual(self.dump(),before)

    def test_configured_interval_rejection_keeps_the_requested_slot(self):
        pet(self.path,self.uid,0x661,settings(mp_seconds=60),'interval')
        use(self.path,self.uid,request(1),'timer-first',now=1000,automatic_use=True)
        before=self.dump()
        with patch('els_server.storage.consumables.time.time',return_value=1040):
            answer=handle(self.session,Event(0x202,kind=0x65e,payload=request(1)),20)
        self.assertEqual(tail(answer[0])[-1],1)
        self.assertEqual(struct.unpack_from('>i',answer[0].payload)[0],1369)
        self.assertEqual(self.dump(),before)
        self.assertEqual(len(use(self.path,self.uid,request(1),'timer-ready',now=1060,automatic_use=True)),2)

    def test_replay_rollback_cold_read_and_manual_independence(self):
        answer=use(self.path,self.uid,request(0),'first',now=1000,automatic_use=True)
        self.assertEqual(tail(answer[0])[2],30.)
        before=self.dump()
        replay=use(self.path,self.uid,request(0),'first',now=self.uid,automatic_use=True)
        self.assertEqual([e.kind for e in replay],[0x65f]);self.assertEqual(tail(replay[0])[0],-1)
        self.assertEqual(self.dump(),before)
        with patch('els_server.storage.consumables.encode_event',side_effect=ValueError('owned encoder fault')):
            with self.assertRaises(ValueError):use(self.path,self.uid,request(0),'fault',now=1030,automatic_use=True)
        self.assertEqual(self.dump(),before)
        cold=LocalAccount(LocalState(self.path,self.uid));cold.enable_characters()
        self.assertEqual(next(i['count'] for i in cold.get_inventory_snapshot()['items'] if i['template']==77000),7)
        save_request(self.path,struct.pack('>i',1)+encode({**empty(),0:item_binding(77000)}),self.uid)
        manual=use(self.path,self.uid,request(0),'manual',now=self.uid)
        self.assertEqual([e.kind for e in manual],[0x114,0x115]);self.assertEqual(tail(manual[0])[2],-1.)
        with self.assertRaises(ConsumableCoolingDown):use(self.path,self.uid,request(0),'early',now=1029.99,automatic_use=True)
        self.assertEqual(len(use(self.path,self.uid,request(0),'ready',now=1030,automatic_use=True)),2)

if __name__=='__main__':unittest.main(verbosity=2)
