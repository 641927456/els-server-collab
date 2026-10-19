"""A decoded C1 alone cannot prove UI, return or reentry."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_clear_return import evaluate
directory=ROOT/'analysis/client-6c6b5180/20261013-192429';s=json.loads((directory/'clear-return-reentry-phase-snapshot.json').read_text(encoding='utf8'))
def accepted(x):return evaluate(x,directory)['isolated_result_ui_return_reentry_verified']
assert accepted(s)
for event in ['native_lifecycle_packet','native_network_npc_death','readonly_clear_state','updated_dungeon_frame']:
 bad=copy.deepcopy(s);bad['rows']=[r for r in bad['rows'] if r.get('payload',{}).get('event')!=event];assert not accepted(bad)
for kind in [0xc1,0x225,0x227,0xb2]:
 bad=copy.deepcopy(s);bad['server']=[e for e in bad['server'] if e.get('kind')!=kind];assert not accepted(bad)
bad=copy.deepcopy(s);bad['visual_review']['screenshots']['clear-ui-8.png']='wrong';assert not accepted(bad)
bad=copy.deepcopy(s);bad['rows'].append({'type':'error','description':'in-phase error'});assert not accepted(bad)
bad=copy.deepcopy(s);bad['rows'].append({'type':'send','payload':{'event':'experimental_empty_clear_dispatch'}});assert not accepted(bad)
bad=copy.deepcopy(s);bad['server'].append({'event':'local_business_response_sent','kind':0xc1});assert not accepted(bad)
print('PASS: missing native/wire/state/pixels, private clear, duplicate result delivery and errors reject clear/return/reentry acceptance.')
