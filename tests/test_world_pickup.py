"""Atomic pickup, current-state retries, ownership and rollback from real D0 wire."""
import hashlib,json,sqlite3,struct,sys,tempfile,uuid
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
from drop_pickup import DROP_ID_XOR
from dungeon_drops import potion_drop_notice
from inventory_items import inventory_payload
source=json.loads((ROOT/'analysis/client-6c6b5180/20261014-002737/world-drop-probe-snapshot.json').read_text(encoding='utf8'))
request=bytes.fromhex(next(e['payload_hex'] for e in source['server'] if e.get('event')=='decoded_client_event' and e.get('kind')==0xd0))
args={'enter_town':True,'enter_dungeon':True,'client_build':'dx11_260923','npc_slot_test':True,'gate_test':True,'population_test':True,'clear_test':True,'reward_test':True,'item_test':True,'drop_probe':True,'drop_test':True}
def session(path):
    account=LocalAccount(LocalState(path));s=LocalSession(account,**args);s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True;s.reward_run_id=str(uuid.uuid4());return s
def issue(s,drop_id):
    xyz=source['issued'][0]['xyz'];s.world_drops[drop_id]={'run_id':s.reward_run_id,'owner':1001,'stage':0,'npc_key':0,'drop_id':drop_id,'template':77000,'xyz':xyz,'payload_hex':potion_drop_notice(drop_id,xyz).payload.hex(),'death_proof_sha256':hashlib.sha256(b'verified test death').hexdigest(),'pickup_committed':False}
def pickup(drop_id,suffix=None):
    b=bytearray(request);struct.pack_into('>I',b,320,drop_id^DROP_ID_XOR)
    if suffix is not None:b=b[:349]+struct.pack('>I',len(suffix))+suffix
    return Event(0x202,performers=(0,),kind=0xd0,payload=bytes(b))
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'save.sqlite3';s=session(path);issue(s,910001);issue(s,910002)
    first=s.handle(pickup(910001));assert [e.kind for e in first]==[0xd1,0xd2,0xd3]
    one=s.account.get_inventory_snapshot();assert one['items'][0]['count']==1 and one['balances']=={'ed':0,'experience':0,'revision':1}
    assert first[-1].payload==inventory_payload(one['items'])
    second=s.handle(pickup(910002));two=s.account.get_inventory_snapshot();assert two['items'][0]['count']==2 and two['balances']['revision']==2
    retry=s.handle(pickup(910001,b'different opaque suffix'));assert [e.kind for e in retry]==[0xd1,0xd3]
    assert retry[-1].payload==inventory_payload(two['items']) and retry[-1].payload!=first[-1].payload
    assert s.account.get_inventory_snapshot()==two and s.pickup_receipt['replayed'] is True
    assert LocalAccount(LocalState(path)).get_inventory_snapshot()==two
    assert s.handle(pickup(910003))==[]
    s.world_drops[910001]['owner']=1002;assert s.handle(pickup(910001))==[];s.world_drops[910001]['owner']=1001
    wrong=Event(0x202,performers=(1002,),kind=0xd0,payload=request);assert s.handle(wrong)==[]
    issue(s,910003);s.gate_stage=1;assert s.handle(pickup(910003))==[];s.gate_stage=0
    with closing(sqlite3.connect(path)) as db,db:db.execute("CREATE TRIGGER fail_pickup BEFORE INSERT ON reward_inventory_receipts BEGIN SELECT RAISE(ABORT,'injected'); END")
    try:s.handle(pickup(910003))
    except sqlite3.IntegrityError:pass
    else:raise AssertionError('Injected receipt failure did not roll back')
    assert s.account.get_inventory_snapshot()==two and s.world_drops[910003]['pickup_committed'] is False
    with closing(sqlite3.connect(path)) as db,db:
        assert db.execute('SELECT COUNT(*) FROM reward_receipts').fetchone()[0]==2
        db.execute('DROP TRIGGER fail_pickup')
    assert [e.kind for e in s.handle(pickup(910003))]==[0xd1,0xd2,0xd3]
    assert s.account.get_inventory_snapshot()['items'][0]['count']==3
with tempfile.TemporaryDirectory() as directory:
    s=session(Path(directory)/'concurrent.sqlite3');issue(s,910001)
    with ThreadPoolExecutor(max_workers=8) as pool:replies=list(pool.map(lambda _:s.handle(pickup(910001)),range(8)))
    assert s.account.get_inventory_snapshot()['items'][0]['count']==1 and sum(any(e.kind==0xd2 for e in r) for r in replies)==1
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'full.sqlite3';s=session(path);issue(s,910001)
    with closing(sqlite3.connect(path)) as db,db:
        for slot in range(36):db.execute('INSERT INTO inventory_items VALUES (?,1001,77000,2,99,6,?)',(1001001+slot,slot))
        db.execute('UPDATE inventory_sequence SET next_uid=1001037')
    before=s.account.get_inventory_snapshot();reply=s.handle(pickup(910001));assert [e.kind for e in reply]==[0xd1] and reply[0].payload==struct.pack('>i',-1)
    assert s.account.get_inventory_snapshot()==before and not s.world_drops[910001]['pickup_committed']
try:LocalSession(drop_test=True)
except ValueError:pass
else:raise AssertionError('Unisolated saved pickup accepted')
print('PASS: pickup grants once, old retries return latest stack, ownership/stage fail closed, receipt failures/full bag roll back and concurrent retries grant once.')
