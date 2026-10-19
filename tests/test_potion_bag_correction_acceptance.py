"""Reject accessory classification, missing native/UI evidence or changed ledger."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_potion_bag_correction import evaluate
path=ROOT/'analysis/client-6c6b5180/20261014-014257/potion-bag-correction-after-ui-retry-snapshot.json'
s=json.loads(path.read_text(encoding='utf8'));assert evaluate(s,path.parent)['potion_bag_correction_verified']
def reject(change):
 v=copy.deepcopy(s);change(v);assert not evaluate(v,path.parent)['potion_bag_correction_verified']
reject(lambda v:v['database']['inventory_items'][0].__setitem__(5,2))
reject(lambda v:v['database']['inventory_items'][0].__setitem__(4,7))
reject(lambda v:v['database']['reward_balances'][0].__setitem__(1,361))
reject(lambda v:v['database']['reward_receipts'][0].__setitem__(3,'00'))
reject(lambda v:v['database']['inventory_sequence'][0].__setitem__(1,1001003))
reject(lambda v:v['database'].__setitem__('migrations',[]))
reject(lambda v:v['identity'].__setitem__('auto_dungeon_entry',True))
reject(lambda v:v.__setitem__('visual_review',None))
reject(lambda v:v.__setitem__('picture_sha256','00'*32))
reject(lambda v:v['server'].append({'event':'local_world_pickup_committed'}))
for event in ('native_owned_economy_sync_consumed','native_inventory_item_inserted','readonly_owned_inventory_frame','original_inventory_open_called'):
 reject(lambda v,e=event:v.__setitem__('rows',[r for r in v['rows'] if r.get('payload',{}).get('event')!=e]))
sync_stamp=next(r['payload']['timestamp'] for r in s['rows'] if r.get('payload',{}).get('event')=='native_owned_economy_sync_consumed')
for row in s['rows']:
 e=row.get('payload',{})
 if e.get('event')=='readonly_owned_inventory_frame' and e['timestamp']>sync_stamp+1000:
  reject(lambda v,t=e['timestamp']:next(r['payload'] for r in v['rows'] if r.get('payload',{}).get('event')=='readonly_owned_inventory_frame' and r['payload']['timestamp']==t).__setitem__('accessory_slots',{'declared_count':1,'items':[{}]}));break
reject(lambda v:v['rows'].append({'type':'send','payload':{'event':'inventory_open_error','error':'injected'}}))
print('PASS: correction acceptance rejects classification/count/ledger changes, missing native slot/UI evidence, bad pixels and probe errors.')
