"""New same-room88E branch; reuse actual TLS reservation/claimed ticket setup."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
foundation=W/'verify_relationship_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
prefix='\n'.join(original.splitlines()[:main.lineno-1]);body=ast.get_source_segment(original,main)
t=ast.parse((W/'verify_wedding_rooms_tls.py').read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in t.body if isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id=='cases'for x in n.targets)))
cases=cases[:cases.index('                manifest=await')]+r'''
                from els_server.storage import weddings
                extra=struct.pack('>iIQ',1,1,uid[3])
                original_ack=wedding.inventory_ack
                def failed(kind,changes=(),*,result=0):
                    if kind==0x88f and result==0:raise ValueError('Owned hall88F encoder')
                    return original_ack(kind,changes,result=result)
                with patch.object(wedding,'inventory_ack',side_effect=failed):
                    answer=await groom.query(0x88e,extra)
                assert answer.payload[:4]!=bytes(4)
                assert read('SELECT count FROM inventory_items WHERE owner=?AND template=277150',(uid[0],))==[(30,)]
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==8
                assert (await groom.query(0x88e,extra)).payload[:4]==bytes(4)
                assert read('SELECT count FROM inventory_items WHERE owner=?AND template=277150',(uid[0],))==[(29,)]
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==9
                assert (await groom.query(0x88e,extra)).payload[:4]!=bytes(4)
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==9
                detail=await groom.query(0x88c,struct.pack('>iB',1,0))
                assert detail.payload[:4]==bytes(4)
                assert all(app.world.weddings.room(app.playing[a])is room for a in aid)
                report['checks'].append('Actual same-room spouse88E/88F and88C use current wedding membership; late ACK encoding rolls back blank and guest letter, one success spends one blank/issues one source-bound letter, duplicate spends nothing and leaves all room actors in place')
'''
start=body.index('            await groom.query(0xc09)');end=body.index("            report['ok']=True",start)
body=body[:start]+cases+body[end:]
body=body.replace("enumerate('AB')","enumerate('ABCD')").replace('groom,bride=peers','groom,bride=peers[:2]')
body=body.replace('base=int(datetime.combine(day,daytime(hour=12),CLIENT_ZONE).timestamp())','base=now-60')
body=body.replace("'owned-relationship-tls-'","'owned-wedding-hall-invite-tls-'").replace("'relationship-tls-'","'wedding-hall-invite-tls-'")
generated=W/'generated-wedding-hall-invite-tls.py';ast.parse(body);generated.write_text(body+'\n','utf8')
exec(compile(prefix,str(foundation),'exec'),globals());exec(compile(body,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
