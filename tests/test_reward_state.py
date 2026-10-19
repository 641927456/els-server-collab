"""Transaction failure/recovery, conflicting retries and concurrent duplicates."""
import concurrent.futures,json,sqlite3,sys,tempfile,uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from reward_state import RewardState,RewardConflict
with tempfile.TemporaryDirectory() as d:
 path=Path(d)/'reward.sqlite3';s=RewardState(path);run=str(uuid.uuid4());calls=[]
 def build(b):calls.append(b);return json.dumps(b,sort_keys=True).encode()
 first=s.grant(run,b'authenticated native Boss death and BB',120,50,build)
 assert first['balances']=={'ed':120,'experience':50,'revision':1} and not first['replayed']
 second=RewardState(path).grant(run,b'authenticated native Boss death and BB',120,50,lambda b:(_ for _ in ()).throw(AssertionError('Retry must use saved response')))
 assert second['response']==first['response'] and second['replayed'] and len(calls)==1
 for proof,ed,xp in [(b'conflicting proof',120,50),(b'authenticated native Boss death and BB',121,50)]:
  try:s.grant(run,proof,ed,xp,build)
  except RewardConflict:pass
  else:raise AssertionError('Conflicting replay accepted')
 assert s.balances()==first['balances']
 fail=str(uuid.uuid4())
 try:s.grant(fail,b'valid evidence',10,20,lambda b:(_ for _ in ()).throw(RuntimeError('Injected encoding failure')))
 except RuntimeError:pass
 else:raise AssertionError('Failure not raised')
 assert s.balances()==first['balances']
 assert not s.grant(fail,b'valid evidence',10,20,build)['replayed']
 duplicate=str(uuid.uuid4())
 def grant_retry(_):return RewardState(path).grant(duplicate,b'same completed run',7,9,build)
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:out=list(pool.map(grant_retry,range(12)))
 assert sum(not r['replayed'] for r in out)==1 and len({r['response'] for r in out})==1
 assert RewardState(path).balances()=={'ed':137,'experience':79,'revision':3}
 # Database failure after the balance update must also roll back the update.
 with closing(sqlite3.connect(path)) as db,db:db.execute("CREATE TRIGGER refuse_receipt BEFORE INSERT ON reward_receipts BEGIN SELECT RAISE(ABORT,'injected insert failure'); END")
 before=s.balances()
 try:s.grant(str(uuid.uuid4()),b'valid evidence',100,100,build)
 except sqlite3.IntegrityError:pass
 else:raise AssertionError('Injected insert failure ignored')
 assert s.balances()==before
 for amount in [-1,True,1.5,2**63]:
  try:s.grant(str(uuid.uuid4()),b'valid evidence',amount,0,build)
  except ValueError:pass
  else:raise AssertionError('Invalid reward accepted')
 assert s.balances()==before
print('PASS: durable cached response, conflicting retry rejection, encoder/insert rollback, concurrent once-only grant and amount bounds; native field integration remains pending.')
