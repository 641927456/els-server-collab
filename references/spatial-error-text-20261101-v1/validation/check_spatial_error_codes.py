"""CI-ready literal guard for the proven native spatial empty-text sentinel."""
from pathlib import Path
import argparse,ast,json

def minus_one(node):
    return isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.USub) and isinstance(node.operand,ast.Constant) and node.operand.value==1

def first_code(node):
    while isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):node=node.left
    if not isinstance(node,ast.Call):return None
    if isinstance(node.func,ast.Name) and node.func.id=='i32' and node.args:return node.args[0]
    if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='struct' and node.func.attr=='pack' and len(node.args)>1:return node.args[1]
    return None

def find(source):
    tree=ast.parse(source);rows=[]
    field_aliases={a.asname or a.name for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module=='els_server.protocol' for a in n.names if a.name=='field_boss_messages'}
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):continue
        keys={k.arg:k.value for k in node.keywords};opcode=None;code=None
        if isinstance(node.func,ast.Name) and node.func.id=='Event' and isinstance(keys.get('kind'),ast.Constant):
            opcode=keys['kind'].value
            if opcode in (0x226,0x228,0x375) and 'payload'in keys:code=first_code(keys['payload'])
        elif isinstance(node.func,ast.Name) and node.func.id=='_reply' and len(node.args)>1 and isinstance(node.args[0],ast.Constant):
            opcode=node.args[0].value
            if opcode in (0x226,0x228,0x375):code=node.args[1]
        elif isinstance(node.func,ast.Attribute) and node.func.attr=='joined' and isinstance(node.func.value,ast.Name) and node.func.value.id in field_aliases:
            opcode=0x375;code=keys.get('result')
        if minus_one(code):rows.append({'line':node.lineno,'opcode':hex(opcode),'source':ast.get_source_segment(source,node)})
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path);ap.add_argument('--self-test',action='store_true');args=ap.parse_args()
    if args.self_test:
        positive=["Event(0x201,kind=0x226,payload=i32(-1)+i32(0)*4)","_reply(0x228,-1)","Event(0x201,kind=0x226,payload=struct.pack('>5i',-1,0,0,0,0))","from els_server.protocol import field_boss_messages as wire\nwire.joined((),None,0,result=-1)"]
        negative=["Event(0x201,kind=0x226,payload=i32(0)+i32(-1)*4)","Event(0x201,kind=0x226,payload=struct.pack('>5i',515,-1,0,0,0))","Event(0x201,kind=0x105,payload=i32(-1))","_reply(0x228,0)","other.joined(result=-1)"]
        assert all(len(find(v))==1 for v in positive) and all(not find(v)for v in negative)
        print(json.dumps(dict(ok=True,positive_cases=len(positive),negative_cases=len(negative))))
    if args.root:
        findings=[dict(path=p.relative_to(args.root).as_posix(),**row) for p in sorted((args.root/'els_server').rglob('*.py')) for row in find(p.read_text('utf8'))]
        print(json.dumps(dict(ok=not findings,findings=findings)))
        if findings:raise SystemExit(1)

if __name__=='__main__':main()
