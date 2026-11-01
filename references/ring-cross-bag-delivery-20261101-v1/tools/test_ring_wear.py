"""Current runtime + one candidate leaf; all test saves stay on G:."""
import importlib.util,json,sqlite3,struct,sys,tempfile,unittest,uuid
from contextlib import closing
from pathlib import Path

ROOT=Path('G:/els');OUT=Path(__file__).resolve().parent
BASE=Path('G:\\els\\releases\\online\\three-activities-integrated-20261101-v1')
CANDIDATE=OUT/'candidate'
sys.dont_write_bytecode=True;sys.path.insert(0,str(BASE))
from els_server.storage import wear_moves as baseline
if '--baseline' not in sys.argv:
    if (CANDIDATE/'els_server/domain/fashion_state.py').exists():
        spec=importlib.util.spec_from_file_location('els_server.domain.fashion_state',CANDIDATE/'els_server/domain/fashion_state.py')
        fashion=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fashion;spec.loader.exec_module(fashion)
        import els_server.domain
        els_server.domain.fashion_state=fashion
    spec=importlib.util.spec_from_file_location('els_server.storage.wear_moves',CANDIDATE/'els_server/storage/wear_moves.py')
    wear=importlib.util.module_from_spec(spec);sys.modules[spec.name]=wear;spec.loader.exec_module(wear)
    import els_server.storage
    els_server.storage.wear_moves=wear
else:wear=baseline
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.storage.characters import BASE_CLASSES
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS,TEMPLATE_BAG_GROUPS
from els_server.game_data import client_data

RINGS=(200700,270974,270975,270976,270977)
NATIVE_WIRES=[]

class RingWearTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='owned-',dir=OUT);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'game.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.session=str(uuid.uuid4());self.sequence=0
    def sql(self,sql,args=()):
        with closing(sqlite3.connect(self.path)) as db,db:return db.execute(sql,args).fetchall()
    def seed(self,uid,t,g,s):self.sql('INSERT INTO inventory_items VALUES (?,1001,?,0,1,?,?)',(uid,t,g,s))
    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:return load_items(db,1001)
    def send(self,a,b,sequence=None,**kw):
        self.sequence+=1
        return wear.move(self.path,struct.pack('>BiBiB',*a,*b,0),1001,account_id=kw.pop('account_id',1),session_id=self.session,sequence=self.sequence if sequence is None else sequence,**kw)
    def unchanged_rejection(self,a,b,text=None,**kw):
        before=self.snapshot();receipts=self.receipts()
        with self.assertRaisesRegex(ValueError,text or '.') :self.send(a,b,**kw)
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.receipts(),receipts)
    def receipts(self):
        if not self.sql("SELECT 1 FROM sqlite_master WHERE name='wear_move_receipts'"):return []
        return self.sql('SELECT * FROM wear_move_receipts ORDER BY operation_id')
    def ice(self,family,cls):
        character=dict(unit_type=family,unit_class=cls,level=99)
        for t,s in FASHION_EQUIP_SLOTS.items():
            if s!=49 or TEMPLATE_BAG_GROUPS[t]!=27:continue
            try:wear.require_wearable(dict(uid=910002,template=t,metadata=0,count=1,group=9,slot=49),character)
            except ValueError:continue
            return t
        self.fail('No legal ice ring for family '+str(family))
    def test_ordinary_rings_replace_ice_and_return_both_tabs_all_families(self):
        for family,cls in BASE_CLASSES.items():
            self.sql('UPDATE characters SET unit_type=?,unit_class=?,level=99 WHERE uid=1001',(family,cls))
            ice=self.ice(family,cls)
            for t in RINGS:
                with self.subTest(family=family,ring=t):
                    self.seed(910001,t,7,0);self.seed(910002,ice,9,49)
                    before=self.snapshot();wire=self.send((7,0),(9,49))
                    self.assertEqual(struct.unpack_from('>I',wire)[0],3)
                    after={i['uid']:i for i in self.snapshot()}
                    self.assertEqual((after[910001]['group'],after[910001]['slot']),(9,49))
                    self.assertEqual((after[910002]['group'],after[910002]['slot']),(27,0))
                    back=self.send((27,0),(9,49));self.assertEqual(self.snapshot(),before)
                    if family==1:NATIVE_WIRES.extend((wire,back))
                    self.sql('DELETE FROM inventory_items WHERE uid IN(910001,910002)')
    def test_single_same_tab_swap_and_unequip(self):
        for i,t in enumerate(RINGS):self.seed(910001+i,t,7,i)
        original=self.snapshot()
        for i,t in enumerate(RINGS):
            self.assertEqual(self.send((7,i),(9,49))[-4:],bytes(4))
            self.send((9,49),(7,i))
        self.assertEqual(self.snapshot(),original)
        self.send((7,0),(9,49));self.send((7,1),(9,49))
        self.assertEqual(next(i for i in self.snapshot() if i['uid']==910001)['slot'],1)
    def test_actual_104_session_dispatch_and_105_response(self):
        from els_server.protocol.protocol_codec import Event
        session=LocalSession(self.account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,normal_equipment_moves_enabled=True)
        session.role='game';session.phase='town_ready';session.completed.add(0x227);session.active_map=self.account.get_location()['map']
        self.seed(910001,200700,7,0);self.seed(910002,self.ice(1,1),9,49)
        reply=session.handle(Event(0x202,kind=0x104,payload=struct.pack('>BiBiB',7,0,9,49,0),performers=(0,)),request_sequence=1)
        ack=[e for e in reply if (e.event_id,e.kind)==(0x201,0x105)]
        self.assertEqual(len(ack),1);self.assertEqual(ack[0].payload[-4:],bytes(4));self.assertEqual(struct.unpack_from('>I',ack[0].payload)[0],3)
        self.assertIsNone(session._wear_rejection)
    def test_receipt_retry_conflict_and_old_two_position_receipts(self):
        self.seed(910001,200700,7,0);self.seed(910002,self.ice(1,1),9,49)
        self.send((7,0),(9,49));seq=self.sequence
        self.send((27,0),(9,49));before=self.snapshot();receipts=self.receipts()
        ack=self.send((7,0),(9,49),sequence=seq)
        self.assertEqual(struct.unpack_from('>I',ack)[0],3);self.assertEqual(self.snapshot(),before);self.assertEqual(self.receipts(),receipts)
        self.unchanged_rejection((7,0),(9,17),'receipt conflict',sequence=seq)
        self.send((9,49),(27,0));seq=self.sequence;before=self.snapshot()
        self.send((9,49),(27,0),sequence=seq);self.assertEqual(self.snapshot(),before)
    def test_occupied_return_slot_and_ciel_side(self):
        ice=self.ice(1,1)
        self.seed(910001,200700,7,0);self.seed(910002,ice,9,49);self.seed(910003,ice,27,0)
        self.send((7,0),(9,49))
        outgoing=next(i for i in self.snapshot() if i['uid']==910002)
        self.assertEqual((outgoing['group'],outgoing['slot']),(27,1))
        self.assertEqual(next(i for i in self.snapshot() if i['uid']==910003)['slot'],0)
        self.sql('DELETE FROM inventory_items WHERE uid IN(910001,910002,910003)')
        self.sql('UPDATE characters SET unit_type=10,unit_class=200,level=99 WHERE uid=1001')
        character=dict(unit_type=10,unit_class=200,level=99)
        ice=None
        for t,s in FASHION_EQUIP_SLOTS.items():
            if s!=61 or TEMPLATE_BAG_GROUPS[t]!=27:continue
            try:wear.require_wearable(dict(uid=910002,template=t,metadata=0,count=1,group=9,slot=61),character)
            except ValueError:continue
            ice=t;break
        self.assertIsNotNone(ice)
        self.seed(910001,184928,7,0);self.seed(910002,ice,9,61)
        before=self.snapshot();self.send((7,0),(9,61));self.send((27,0),(9,61));self.assertEqual(self.snapshot(),before)
    def test_full_outgoing_bag_rolls_back(self):
        ice=self.ice(1,1);self.seed(910001,200700,7,0);self.seed(910002,ice,9,49)
        with closing(sqlite3.connect(self.path)) as db,db:
            from els_server.storage.bag_capacity import grant_starting_fashion
            grant_starting_fashion(db,1001)
            db.executemany('INSERT INTO inventory_items VALUES (?,1001,?,0,1,27,?)',[(920000+s,ice,s) for s in range(1120)])
        self.unchanged_rejection((7,0),(9,49),'outgoing costume bag full')
    def test_effect_exclusion_wrong_slot_and_owner_still_rejected(self):
        self.seed(910001,270976,7,0);self.seed(910002,118839,9,41)
        self.unchanged_rejection((7,0),(9,49),'Ring effect group')
        self.sql('DELETE FROM inventory_items WHERE uid=910002')
        for slot in (17,41,54):self.unchanged_rejection((7,0),(9,slot))
        self.unchanged_rejection((7,0),(9,49),'owner mismatch',account_id=2)
    def test_locked_timed_uid_children_cold_read_and_precommit_failure(self):
        self.seed(910001,200700,7,0);self.seed(910002,self.ice(1,1),9,49)
        from els_server.storage.item_expiration import assign
        from els_server.storage.item_locks import assign as set_lock
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            for uid in (910001,910002):assign(db,1001,uid,2100000000);set_lock(db,1001,uid,2100000000)
        before={i['uid']:i for i in self.snapshot()};calls=0
        def stale():
            nonlocal calls
            calls+=1
            if calls==3:raise ValueError('stale before commit')
        self.unchanged_rejection((7,0),(9,49),'stale before commit',validate=stale)
        self.send((7,0),(9,49))
        # Every snapshot uses a newly opened SQLite connection.
        after={i['uid']:i for i in self.snapshot()}
        for uid in (910001,910002):self.assertEqual({k:v for k,v in before[uid].items()if k not in ('group','slot')},{k:v for k,v in after[uid].items()if k not in ('group','slot')})

if __name__=='__main__':
    if '--baseline' in sys.argv:
        case=RingWearTests('test_ordinary_rings_replace_ice_and_return_both_tabs_all_families');case.setUp()
        try:
            case.seed(910001,200700,7,0);case.seed(910002,case.ice(1,1),9,49)
            case.unchanged_rejection((7,0),(9,49),'Wear item bag classification')
            print('BASELINE reproduced: ordinary rage ring replacing an ice ring raises Wear item bag classification; inventory unchanged')
        finally:case.doCleanups()
    else:
        selected=[a for a in sys.argv[1:] if a.startswith('test_')]
        suite=unittest.TestSuite(RingWearTests(name) for name in selected) if selected else unittest.defaultTestLoader.loadTestsFromTestCase(RingWearTests)
        for name in (() if selected else ('test_owned_wear','test_ring2_artifact_wear')):
            spec=importlib.util.spec_from_file_location(name,ROOT/('collaboration/els-server-collab/tests/'+name+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        if result.wasSuccessful() and NATIVE_WIRES:
            (OUT/('native-wires-v2.json' if '--candidate-v2' in sys.argv else 'native-wires.json')).write_text(json.dumps([w.hex() for w in NATIVE_WIRES]),'utf8')
        sys.exit(not result.wasSuccessful())
