from pathlib import Path
source=Path('G:/els/analysis/pet-pickup-latency-20261104-v1/verify_party.py').read_text('utf8')
assert source.count('party-candidate.json')==1
exec(compile(source.replace('party-candidate.json','checked-save-reuse-party-tests.json'),'owned-selection-party','exec'))
