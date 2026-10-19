"""A Boss receipt alone cannot prove native clear/pickup/return behavior."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_boss_drop_clear import evaluate
p=ROOT/'analysis/client-6c6b5180/20261014-030603/boss-drop-clear-snapshot.json';s=json.loads(p.read_text(encoding='utf8'));assert evaluate(s,p.parent)['boss_ground_pickup_clear_return_verified']
def reject(f):
 v=copy.deepcopy(s);f(v);assert not evaluate(v,p.parent)['boss_ground_pickup_clear_return_verified']
reject(lambda v:v['database']['inventory_items'][0].__setitem__(4,24))
reject(lambda v:v['database']['inventory_items'][0].__setitem__(5,2))
reject(lambda v:v['database']['reward_receipts'].pop())
reject(lambda v:v.__setitem__('baseline_sha256','0'*64))
reject(lambda v:v.__setitem__('visual_review',None))
for event in ('original_world_drop_created','native_lifecycle_packet','original_d0_semantics_and_wire','original_pickup_response_consumed','readonly_owned_inventory_frame'):
 reject(lambda v,e=event:v.__setitem__('rows',[r for r in v['rows'] if r.get('payload',{}).get('event')!=e]))
for event in ('local_world_pickup_committed','local_dungeon_reward_committed','local_world_drop_issued','business_phase'):
 reject(lambda v,e=event:v.__setitem__('server',[r for r in v['server'] if r.get('event')!=e]))
reject(lambda v:v['rows'].append({'type':'send','payload':{'event':'world_drop_observer_error'}}))
print('PASS: Boss acceptance rejects missing native drop/wire/clear/return, changed ledger, wrong bag/count and unreviewed pixels.')
