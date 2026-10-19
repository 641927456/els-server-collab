"""Reject weak or inconsistent corrected pickup evidence."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_corrected_world_pickup import evaluate
p=ROOT/'analysis/client-6c6b5180/20261014-022650/corrected-world-pickup-snapshot.json';s=json.loads(p.read_text(encoding='utf8'));assert evaluate(s,p.parent)['corrected_original_pickup_saved_verified']
def reject(change):
 v=copy.deepcopy(s);change(v);assert not evaluate(v,p.parent)['corrected_original_pickup_saved_verified']
reject(lambda v:v['identity'].__setitem__('drop_test',False))
reject(lambda v:v.__setitem__('baseline_sha256','00'*32))
reject(lambda v:v['database']['inventory_items'][0].__setitem__(5,2))
reject(lambda v:v['database']['inventory_items'][0].__setitem__(4,6))
reject(lambda v:v['database']['reward_balances'][0].__setitem__(1,361))
reject(lambda v:v['database']['inventory_sequence'][0].__setitem__(1,1001003))
reject(lambda v:v['database']['reward_receipts'].pop())
reject(lambda v:v['database']['reward_inventory_receipts'].pop())
reject(lambda v:v.__setitem__('visual_review',None))
reject(lambda v:v['pictures'].__setitem__('corrected-live-pickup-town-bag.png','00'*32))
reject(lambda v:v['server'].append({'event':'local_dungeon_reward_committed'}))
for event in ('original_d0_semantics_and_wire','original_pickup_response_consumed','readonly_dungeon_inventory_frame','original_inventory_open_called'):
 reject(lambda v,e=event:v.__setitem__('rows',[r for r in v['rows'] if r.get('payload',{}).get('event')!=e]))
reject(lambda v:v['rows'].append({'type':'send','payload':{'event':'inventory_open_error','error':'injected'}}))
print('PASS: corrected pickup acceptance rejects wrong bag/count, changed ledger, missing native wire/UI/slot evidence and errors.')
