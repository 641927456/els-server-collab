"""Compile-only source boundary for the reviewed EP credit guard; no imports/SQL."""
import ast,hashlib,pathlib,sys
EXPECTED = {'ensure': 'de027015a06a9e621b73e44889f9039f4f008ba0ae826e8e518684d9b321f677', 'balance': '790c9f5f027d7cf8402fce86569f2f2d900bf270147cf73b79eac85c9b077c6a', 'credit': 'bec336b63c7c95e28189bd3e9cfc3c7ec177411c122f93f6307b01bba8f152d9'}
path=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[1]/'els_server/storage/ep_points.py'
raw=path.read_bytes()
compile(raw,str(path),'exec')
tree=ast.parse(raw)
functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
if set(functions)!=set(EXPECTED):raise SystemExit('EP source function scope changed; review required')
for name,expected in EXPECTED.items():
 actual=hashlib.sha256(ast.dump(functions[name],include_attributes=False).encode()).hexdigest()
 if actual!=expected:raise SystemExit('EP function boundary changed: '+name)
print('EP source compile/boundary passed; no SQL or runtime execution')
