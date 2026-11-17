"""Requalify the shared dispatcher with the unchanged four-role wedding cases."""
from pathlib import Path
import ast
import bootstrap as env
W=Path(__file__).resolve().parent;J=W.parent/'wedding-v1'
foundation=J/'verify_relationship_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
prefix='\n'.join(original.splitlines()[:main.lineno-1]).replace("B=W/'test-source-v1'","B=env.BASE")
body=ast.get_source_segment(original,main)
def literal(path,name):
    t=ast.parse(path.read_text('utf8'))
    return ast.literal_eval(next(n.value for n in t.body if isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id==name for x in n.targets)))
cases=literal(J/'verify_wedding_rooms_tls.py','cases')
extra=literal(J/'verify_wedding_transport_snapshot_tls.py','cases')
needle='                manifest=await app.call(app.world.dungeons.manifest,app,aid[0])'
assert needle in cases;cases=cases.replace(needle,extra+needle).replace('417/418/F3','417/418/D9')
start=body.index('            await groom.query(0xc09)');end=body.index("            report['ok']=True",start)
body=body[:start]+cases+body[end:]
body=body.replace("enumerate('AB')","enumerate('ABCD')").replace('groom,bride=peers','groom,bride=peers[:2]')
body=body.replace('base=int(datetime.combine(day,daytime(hour=12),CLIENT_ZONE).timestamp())','base=now-60')
body=body.replace("'owned-relationship-tls-'","'owned-common-wedding-routing-tls-'").replace("'relationship-tls-'","'common-wedding-routing-TLS-'")
ast.parse(body);generated=W/'generated-common-wedding-routing-TLS.py';generated.write_text(body+'\n','utf8')
exec(compile(prefix,str(foundation),'exec'),globals());exec(compile(body,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
