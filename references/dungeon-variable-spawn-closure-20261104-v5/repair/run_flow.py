import collections,json,sys,time
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];sys.dont_write_bytecode=True;R=ROOT/json.loads((ROOT/'releases/online/current.json').read_bytes())['path'];sys.path[:0]=[str(R),str(ROOT/'tools')]
from els_server.game_data import client_data
import read_kl_bytecode as kl
from flow_sources import Flow
enums=client_data().resource('Enum.lua');all_sources='--all'in sys.argv;inputs=json.loads((W/('all-variable-call-inputs.private.json'if all_sources else'variable-call-inputs.private.json')).read_bytes());out=[]
selected={int(x)for x in sys.argv[1:]if x!='--all'}
for row in inputs:
 if selected and row['template']not in selected:continue
 start=time.monotonic()
 try:
  flow=Flow(kl.read(Path(row['path']).read_bytes()),enums);calls=flow.spawn_results();wanted={(r['prototype'],r['call_pc'])for r in row['calls']};calls=[r for r in calls if(r['prototype'],r['call_pc'])in wanted];assert len(calls)==len(wanted)
  result=dict(template=row['template'],script=row['script'],sha256=row['sha256'],calls=calls,all_closed=all(not c['unknown']for c in calls),nodes=len(flow.nodes),seconds=time.monotonic()-start)
 except Exception as exc:result=dict(template=row['template'],script=row['script'],error=repr(exc))
 out.append(result);print(json.dumps(dict(template=row['template'],closed=result.get('all_closed'),error=result.get('error'),seconds=round(time.monotonic()-start,2))),flush=True)
name='flow-results'+('-all'if all_sources else'')+('-'+ '-'.join(map(str,sorted(selected)))if selected else'')+'.private.json';(W/name).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(dict(scripts=len(out),closed=sum(r.get('all_closed',False)for r in out),errors=sum('error'in r for r in out),calls=sum(len(r.get('calls',[]))for r in out),open=sum(bool(c['unknown'])for r in out for c in r.get('calls',[])))))
