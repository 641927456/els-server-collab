from pathlib import Path
p=Path('G:/els/analysis/pet-pickup-latency-20261104-v1/verify_runtime.py')
exec(compile(p.read_text('utf8'),str(p),'exec'))
