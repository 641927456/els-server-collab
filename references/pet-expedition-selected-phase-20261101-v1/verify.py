from pathlib import Path
import ast,hashlib,json
O=Path(__file__).resolve().parent;R=O.parents[1]
c=json.loads((O/'source-contract.json').read_bytes());assert c['issue']==714 and len(c['files'])==1
f=c['files'][0];p=R/f['source'];assert p.is_relative_to(O/'source/shared')and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'];ast.parse(p.read_text('utf8'))
t=json.loads((O/'lifecycle-qualified.json').read_bytes());g=json.loads((O/'GUI-qualification.json').read_bytes())
assert t['ok']and t['original_unselected_unknown_character_reproduced']and t['broken_selected_actor_error_not_swallowed']
assert g['ok']and 20000<=g['character_selection_held_ms']<600000 and g['human_normal_selection_and_game_entry']and g['notification_errors']==0
print(json.dumps(dict(ok=True,delivery_leaves=1,recorded_selected_phase_lifecycle=True,recorded_GUI=True,runtime_tests_reexecuted=False)))
