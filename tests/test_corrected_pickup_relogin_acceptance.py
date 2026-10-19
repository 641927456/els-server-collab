"""Reject login grants, slot regressions and missing original restoration evidence."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_corrected_pickup_relogin import evaluate
p=ROOT/'analysis/client-6c6b5180/20261014-024715/corrected-pickup-relogin-snapshot.json';s=json.loads(p.read_text(encoding='utf8'));assert evaluate(s,p.parent)['corrected_original_pickup_relogin_verified']
def reject(change):
 v=copy.deepcopy(s);change(v);assert not evaluate(v,p.parent)['corrected_original_pickup_relogin_verified']
reject(lambda v:v['identity'].__setitem__('auto_dungeon_entry',True))
reject(lambda v:v['identity'].__setitem__('pid',38168))
reject(lambda v:v['database']['inventory_items'][0].__setitem__(4,6))
reject(lambda v:v['database']['inventory_items'][0].__setitem__(5,2))
reject(lambda v:v['database']['reward_balances'][0].__setitem__(3,8))
reject(lambda v:v['database']['reward_receipts'].pop())
reject(lambda v:v['database']['inventory_sequence'][0].__setitem__(1,1001003))
reject(lambda v:v.__setitem__('baseline_sha256','00'*32))
reject(lambda v:v.__setitem__('visual_review',None))
reject(lambda v:v['server'].append({'event':'local_world_pickup_committed'}))
for event in ('native_owned_economy_sync_consumed','native_inventory_item_inserted','readonly_owned_inventory_frame','original_inventory_open_called'):
 reject(lambda v,e=event:v.__setitem__('rows',[r for r in v['rows'] if r.get('payload',{}).get('event')!=e]))
reject(lambda v:v['rows'].append({'type':'send','payload':{'event':'inventory_open_error','error':'injected'}}))
print('PASS: real saved pickup login acceptance rejects duplicate grants, count/bag/ledger changes and missing native restoration/UI evidence.')
