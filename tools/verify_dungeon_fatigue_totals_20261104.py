"""Verify pinned totals and stable receipt scopes without private runtime data."""
from pathlib import Path
import hashlib,importlib.util,json
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'references/dungeon-fatigue-total-20261104-v1'
read=lambda p:json.loads(p.read_bytes())
c=read(A/'source-contract.json')
for rel,row in c['files'].items():assert hashlib.sha256((A/row['source']).read_bytes()).hexdigest()==row['sha256']
assert hashlib.sha256((A/'website-audit.json').read_bytes()).hexdigest()==c['website_audit_sha256']
p=A/'source/els_server/domain/normal_fatigue_rules.py';spec=importlib.util.spec_from_file_location('fatigue_rules',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
raw=(A/'source/els_server/data/normal_fatigue.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==m.DATA_SHA;data=json.loads(raw)
audit=read(A/'website-audit.json');assert audit['passed']==260 and audit['failed']==0
fixed=paid=0
for reference in audit['rows']:
 mid=str(reference['map']);r=data['routes'][mid];old=reference['previous_rule']
 if old['cost']==0:assert r==old;continue
 paid+=1;assert sum(r['stage_costs'].values())==reference['total']
 if r['basis']=='current_client_explicit':fixed+=1;assert all(r[k]==v for k,v in old.items())
 else:assert r==old
 contexts=[]
 for stage,amount in r['stage_costs'].items():
  context=dict(epoch='run1',reward_run='reward1',owner=1001,dungeon=int(mid),stage=int(stage),part=0,visits=1,graph_sha256=r['graph_sha256'])
  stable,value=m.debit(r,context);assert value==amount
  assert m.debit(r,dict(context,part=99,visits=17))==(stable,value)
  assert m.debit(r,dict(context,epoch='run2'))[0]!=stable
  assert m.debit(r,dict(context,owner=1002))[0]!=stable
  contexts.append(stable)
 assert len({json.dumps(x,sort_keys=True)for x in contexts})==len(contexts)
assert fixed==91 and paid==223
print(json.dumps(dict(ok=True,routes=260,fixed_paid_routes=fixed,paid_routes=paid,scope='source totals and stable replay identity')))
