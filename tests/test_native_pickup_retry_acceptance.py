"""Do not accept a local replay assertion without actual wire/native/save evidence."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_native_pickup_retry import evaluate
s=json.loads((ROOT/'analysis/client-6c6b5180/20261014-024715/native-pickup-retry-snapshot.json').read_text(encoding='utf8'))
assert evaluate(s)['native_network_duplicate_verified']
def reject(f):
 v=copy.deepcopy(s);f(v);assert not evaluate(v)['native_network_duplicate_verified']
reject(lambda v:v['database']['inventory_items'][0].__setitem__(4,10))
reject(lambda v:v['database']['reward_balances'][0].__setitem__(1,361))
reject(lambda v:v['database']['reward_receipts'].pop())
reject(lambda v:v.__setitem__('baseline_sha256','0'*64))
for name in ('native_pickup_retry_begin','native_pickup_retry_returned','original_d0_semantics_and_wire','original_pickup_response_consumed','native_inventory_item_inserted','readonly_dungeon_inventory_frame'):
 reject(lambda v,n=name:v.__setitem__('rows',[r for r in v['rows'] if r.get('payload',{}).get('event')!=n]))
for name in ('decoded_client_event','local_world_pickup_committed','local_world_pickup_replayed','local_world_drop_issued'):
 reject(lambda v,n=name:v.__setitem__('server',[e for e in v['server'] if e.get('event')!=n]))
reject(lambda v:v['rows'].append({'type':'send','payload':{'event':'native_pickup_retry_error'}}))
print('PASS: duplicate acceptance requires native call, distinct network requests, single receipt, exact saved count and native updates.')
