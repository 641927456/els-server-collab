"""Real relog evidence must reject lost items, duplicate grants and wrong identity."""
import copy
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verify_inventory_relogin import evaluate
run = ROOT / 'analysis/client-6c6b5180/20261013-225304'
source = json.loads((run / 'saved-inventory-login-snapshot.json').read_text(encoding='utf8'))
assert evaluate(source, run)['isolated_saved_inventory_native_relogin_verified']

def reject(edit):
    sample = copy.deepcopy(source)
    edit(sample)
    assert not evaluate(sample, run)['isolated_saved_inventory_native_relogin_verified']

reject(lambda s: s['database']['items'][0].update(count=6))
reject(lambda s: s['database']['sequence'][0].__setitem__(1, 1001003))
reject(lambda s: s['database']['item_receipts'].clear())
reject(lambda s: s['identity'].update(pid=26644))
reject(lambda s: s['identity'].update(auto_dungeon_entry=True))
reject(lambda s: s.update(prior_grant_snapshot_sha256='0' * 64))
for event in ('native_owned_economy_sync_consumed', 'native_inventory_item_inserted', 'readonly_native_inventory_slots', 'readonly_owned_inventory_frame', 'readonly_owned_economy'):
    reject(lambda s, event=event: s.update(rows=[r for r in s['rows'] if r.get('payload', {}).get('event') != event]))
reject(lambda s: s['server'].append({'event': 'local_dungeon_reward_committed'}))
reject(lambda s: s['rows'].append({'type': 'extension_error'}))
print('PASS: new native login restores identical item and wallet; missing/conflicting/duplicate evidence rejected.')
