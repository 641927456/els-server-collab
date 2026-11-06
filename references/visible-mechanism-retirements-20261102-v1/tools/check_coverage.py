"""CI check for the reviewed retirement family; baseline fails, candidate passes."""
import argparse,contextlib,io,json,runpy,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--runtime',required=True);p.add_argument('--candidate',action='store_true');a=p.parse_args()
manifest=json.loads((HERE/'candidate-manifest.json').read_bytes())
excluded={r['script']for r in manifest['triage']if r['verdict']!='missing_source_retirement'}
sys.argv=['audit-visible','--runtime',a.runtime]+(['--candidate']if a.candidate else [])
with contextlib.redirect_stdout(io.StringIO()):scope=runpy.run_path(str(HERE/'audit_visible.py'))
rows=scope['rows']
uncovered=[r for r in rows if r['coverage']=='unlisted'and r['living_states_invincible']and not r['source']['boss']and r['script']not in excluded]
result=dict(ok=not uncovered,entries=len(scope['routes']),candidate=a.candidate,reviewed_missing=len(uncovered),uncovered=[dict(dungeon=r['dungeon'],stage=r['stage'],part=r['part'],template=r['source']['template'],source_index=r['source']['source_index'],script=r['script'])for r in uncovered],unparsed_scripts=len(scope['missing_tables']))
(HERE/('coverage-candidate.json'if a.candidate else 'coverage-baseline.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in result.items()if k!='uncovered'},ensure_ascii=False));sys.exit(bool(uncovered))
