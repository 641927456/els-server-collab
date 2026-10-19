"""Do not claim native inventory pixels when callbacks or saved items disagree."""
import copy
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verify_inventory_window import evaluate
run = ROOT / 'analysis/client-6c6b5180/20261013-225304'
source = json.loads((run / 'inventory-window-phase-snapshot.json').read_text(encoding='utf8'))
assert evaluate(source, run)['inventory_icon_quantity_wallet_verified']

def reject(edit):
    sample = copy.deepcopy(source)
    edit(sample)
    assert not evaluate(sample, run)['inventory_icon_quantity_wallet_verified']

reject(lambda s: s['visual_review'].update(visible_quantity=6))
reject(lambda s: s['visual_review'].update(visible_ed=480))
reject(lambda s: s['visual_review'].update(inventory_visible=False))
reject(lambda s: s['visual_review'].update(sha256='0'*64))
reject(lambda s: s['database']['items'][0].__setitem__(3, 6))
reject(lambda s: s['database'].update(receipt_count=4))
reject(lambda s: s['identity'].update(pid=0))
for event in ('original_inventory_open_called', 'readonly_owned_inventory_frame'):
    reject(lambda s, event=event: s.update(rows=[r for r in s['rows'] if r.get('payload', {}).get('event') != event]))
reject(lambda s: s['rows'].append({'type': 'extension_error'}))
print('PASS: saved native inventory, original open/tab and reviewed icon/count/wallet agree; incomplete/conflicting evidence rejected.')
