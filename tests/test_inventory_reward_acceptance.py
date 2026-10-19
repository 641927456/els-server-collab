"""Reject a claimed real grant when its native slot or durable evidence is missing."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_inventory_reward import evaluate
run=ROOT/'analysis/client-6c6b5180/20261013-221244';source=json.loads((run/'inventory-reward-phase-snapshot.json').read_text(encoding='utf8'))
assert evaluate(source,run)['isolated_native_item_reward_saved_verified']
def reject(f):
 s=copy.deepcopy(source);f(s);assert not evaluate(s,run)['isolated_native_item_reward_saved_verified']
reject(lambda s:s['database']['items'][0].update(count=6))
reject(lambda s:s['database']['item_receipts'].clear())
reject(lambda s:s['database']['balances'][0].__setitem__(1,480))
reject(lambda s:s['identity'].update(item_test=False))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='native_inventory_item_inserted']))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='readonly_native_inventory_slots']))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='readonly_owned_inventory_frame']))
reject(lambda s:s.update(rows=[r for r in s['rows'] if r.get('payload',{}).get('event')!='native_owned_economy_sync_consumed']))
reject(lambda s:s['rows'].append({'type':'send','payload':{'event':'private_item_body_decoded'}}))
reject(lambda s:s['rows'].append({'type':'extension_error'}))
reject(lambda s:s['server'].append({'event':'local_business_response_sent','kind':0xc1}))
print('PASS: real item receipt/parse/insert/live slot agree; missing, private, duplicate or conflicting evidence rejected.')
