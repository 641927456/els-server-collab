from pathlib import Path
H=Path(__file__).resolve().parent
source=(H/'verify_selection_party.py').read_text('utf8').replace('selection-scope-party-tests.json','fatigue-snapshot-reuse-party-tests.json')
exec(compile(source,'owned-fatigue-snapshot-party','exec'))
