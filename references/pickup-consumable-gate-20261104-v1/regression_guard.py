"""CI-ready guard for the three demonstrated dispatch/projection regressions."""
import argparse,ast,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--overlay',type=Path);p.add_argument('--expect-findings',action='store_true');args=p.parse_args();findings=[]
for base in(args.root/'els_server').rglob('*.py'):
 relative=base.relative_to(args.root);path=args.overlay/relative if args.overlay and(args.overlay/relative).exists()else base
 tree=ast.parse(path.read_bytes());aliases=set()
 for n in ast.walk(tree):
  if isinstance(n,ast.ImportFrom)and n.module=='els_server.storage.titles':aliases.update(a.asname or a.name for a in n.names if a.name=='snapshot')
 def title_call(n):
  return isinstance(n,ast.Call)and(isinstance(n.func,ast.Name)and n.func.id in aliases or isinstance(n.func,ast.Attribute)and n.func.attr=='snapshot'and isinstance(n.func.value,ast.Name)and n.func.value.id=='titles')
 for n in ast.walk(tree):
  scalar=isinstance(n,ast.Subscript)and isinstance(n.slice,ast.Constant)and n.slice.value=='title'and title_call(n.value)
  getter=isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='get'and n.args and isinstance(n.args[0],ast.Constant)and n.args[0].value=='title'and title_call(n.func.value)
  if scalar or getter:findings.append(dict(rule='scalar_title_uses_full_missions',file=relative.as_posix(),line=n.lineno))
  if isinstance(n,ast.If)and relative.name=='scene_actor_retirements.py':
   test=ast.unparse(n.test)
   if "report['flag']"in test and'native_class'in test and any(isinstance(x,ast.Return)and isinstance(x.value,ast.Constant)and x.value.value is None for x in n.body):findings.append(dict(rule='finite_retirement_steals_ordinary_report',file=relative.as_posix(),line=n.lineno))
  if isinstance(n,ast.If)and relative.name=='elixir_flow.py'and'part_end_notified'in ast.unparse(n.test)and any(isinstance(x,ast.Return)for x in n.body):findings.append(dict(rule='elixir_rejects_loaded_part_end',file=relative.as_posix(),line=n.lineno))
  if isinstance(n,ast.If)and relative.name=='apple_consumables.py'and isinstance(n.test,ast.BoolOp)and isinstance(n.test.op,ast.Or)and any(isinstance(x,ast.Attribute)and x.attr=='part_end_notified'for x in n.test.values)and any(isinstance(x,ast.Return)and isinstance(x.value,ast.Constant)and x.value.value is False for x in n.body):findings.append(dict(rule='consumable_rejects_loaded_part_end',file=relative.as_posix(),line=n.lineno))
print(json.dumps(dict(findings=findings,count=len(findings))))
raise SystemExit(0 if bool(findings)==args.expect_findings else 1)
