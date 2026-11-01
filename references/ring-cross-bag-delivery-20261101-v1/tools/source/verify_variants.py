"""Bounded cross-tab wear variant regression, no live state or game access."""
import hashlib,importlib.util,json,sqlite3,struct,sys,tempfile,unittest,uuid
from contextlib import closing
from pathlib import Path

ROOT=Path('G:/els');OUT=Path(__file__).resolve().parent
BASE=ROOT/'releases/local/local-native-field-entry-identity-20261101-v1'
CANDIDATE=OUT/('candidate-v2' if '--candidate-v2' in sys.argv else 'candidate')
sys.dont_write_bytecode=True;sys.path.insert(0,str(BASE))
from els_server.storage import wear_moves as baseline
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS,TEMPLATE_BAG_GROUPS,VERIFIED_TEMPLATES,validate_item
from els_server.game_data import client_data
if (CANDIDATE/'els_server/domain/fashion_state.py').exists():
    spec=importlib.util.spec_from_file_location('els_server.domain.fashion_state',CANDIDATE/'els_server/domain/fashion_state.py')
    fashion=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fashion;spec.loader.exec_module(fashion)
    import els_server.domain
    els_server.domain.fashion_state=fashion
spec=importlib.util.spec_from_file_location('candidate_wear_moves',CANDIDATE/'els_server/storage/wear_moves.py')
candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
FINDINGS=[]

def eligible_pairs():
    names={v:k for k,v in client_data().resource('Enum.lua')['NOW_EQIP_SLOT_ID'].items()}
    rows=[]
    for family,cls,minor in ((1,1,False),(10,200,True)):
        pairs={}
        for t,s in FASHION_EQUIP_SLOTS.items():
            g=TEMPLATE_BAG_GROUPS[t]
            if g not in (7,27) or names.get(s,'').startswith('NESI_MINORUNIT_')!=minor or g in pairs.get(s,{}):continue
            item=dict(uid=1,template=t,metadata=VERIFIED_TEMPLATES[t],count=1,group=9,slot=s)
            try:
                validate_item(item)
                baseline.require_wearable(item,dict(unit_type=family,unit_class=cls,level=99))
            except ValueError:continue
            pairs.setdefault(s,{})[g]=t
        for s,templates in sorted(pairs.items()):
            if len(templates)==2:rows.append(dict(family=family,unit_class=cls,slot=s,slot_name=names[s],templates=templates))
    return rows

class CrossTabVariants(unittest.TestCase):
    def test_all_qualified_positions_baseline_and_candidate(self):
        pairs=eligible_pairs();self.assertEqual(len(pairs),33)
        with tempfile.TemporaryDirectory(prefix='owned-variants-',dir=OUT) as folder:
            path=Path(folder)/'game.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
            session=str(uuid.uuid4());sequence=0
            def snapshot():
                with closing(sqlite3.connect(path)) as db:return load_items(db,1001)
            def send(module,a,b):
                nonlocal sequence
                sequence+=1
                return module.move(path,struct.pack('>BiBiB',*a,*b,0),1001,account_id=1,session_id=session,sequence=sequence)
            for pair in pairs:
                with self.subTest(slot=pair['slot_name']):
                    s=pair['slot'];first=pair['templates'][7];second=pair['templates'][27]
                    with closing(sqlite3.connect(path)) as db,db:
                        db.execute('UPDATE characters SET unit_type=?,unit_class=?,level=99 WHERE uid=1001',(pair['family'],pair['unit_class']))
                        db.execute('INSERT INTO inventory_items VALUES (910001,1001,?,?,1,7,0)',(first,VERIFIED_TEMPLATES[first]))
                        db.execute('INSERT INTO inventory_items VALUES (910002,1001,?,?,1,9,?)',(second,VERIFIED_TEMPLATES[second],s))
                    original=snapshot()
                    with self.assertRaisesRegex(ValueError,'Wear item bag classification'):send(baseline,(7,0),(9,s))
                    self.assertEqual(snapshot(),original)
                    forward=send(candidate,(7,0),(9,s));old_seq=sequence
                    after=snapshot();by={i['uid']:i for i in after}
                    self.assertEqual((by[910001]['group'],by[910001]['slot']),(9,s))
                    self.assertEqual((by[910002]['group'],by[910002]['slot']),(27,0))
                    self.assertEqual(struct.unpack_from('>I',forward)[0],3);self.assertEqual(forward[-4:],bytes(4))
                    # Reverse replacement must return the ordinary costume to7.
                    backward=send(candidate,(27,0),(9,s));self.assertEqual(snapshot(),original)
                    # Retry must include all three original positions and leave
                    # the reversed, current state intact.
                    retry=candidate.move(path,struct.pack('>BiBiB',7,0,9,s,0),1001,account_id=1,session_id=session,sequence=old_seq)
                    self.assertEqual(struct.unpack_from('>I',retry)[0],3);self.assertEqual(snapshot(),original)
                    if '--candidate-v2' in sys.argv:
                        # The retained helper uses the same replacement plan.
                        legacy_forward=fashion.move_fashion(path,struct.pack('>BiBiB',7,0,9,s,0),1001)
                        self.assertEqual(struct.unpack_from('>I',legacy_forward)[0],3)
                        fashion.move_fashion(path,struct.pack('>BiBiB',27,0,9,s,0),1001)
                        self.assertEqual(snapshot(),original)
                    with closing(sqlite3.connect(path)) as db,db:
                        self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
                        db.execute('DELETE FROM inventory_items WHERE uid IN(910001,910002)')
                    FINDINGS.append(dict(**pair,baseline_rejected=True,candidate_round_trip=True,replay_current_state=True,forward_sha256=hashlib.sha256(forward).hexdigest(),backward_sha256=hashlib.sha256(backward).hexdigest()))

    def test_counterexamples_are_preserved(self):
        # Wrong explicit bag and wrong worn slot are not automatic replacements.
        with tempfile.TemporaryDirectory(prefix='owned-variants-',dir=OUT) as folder:
            path=Path(folder)/'game.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('INSERT INTO inventory_items VALUES (910001,1001,200700,0,1,7,0)')
            for a,b in (((7,0),(27,0)),((7,0),(9,17)),((7,0),(9,43))):
                with self.subTest(source=a,destination=b):
                    with closing(sqlite3.connect(path)) as db:before=load_items(db,1001)
                    with self.assertRaises(ValueError):candidate.move(path,struct.pack('>BiBiB',*a,*b,0),1001,account_id=1,session_id=str(uuid.uuid4()),sequence=1)
                    with closing(sqlite3.connect(path)) as db:self.assertEqual(load_items(db,1001),before)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CrossTabVariants))
    summary=dict(passed=result.wasSuccessful(),baseline=str(BASE),candidate_sha256=hashlib.sha256((CANDIDATE/'els_server/storage/wear_moves.py').read_bytes()).hexdigest(),test_methods=result.testsRun,baseline_reproductions=len(FINDINGS),new_non_ring_positions=sum(not p['slot_name'].endswith('_AC_AVATAR_RING') for p in FINDINGS),candidate_round_trips=len(FINDINGS),legacy_helper_round_trips=len(FINDINGS) if '--candidate-v2' in sys.argv else 0,replay_cases=len(FINDINGS),cases=FINDINGS,live_state_access=False,natural_GUI=False)
    (OUT/('variants-verification-v2.json' if '--candidate-v2' in sys.argv else 'variants-verification.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({k:v for k,v in summary.items() if k!='cases'},ensure_ascii=False))
    sys.exit(not result.wasSuccessful())
