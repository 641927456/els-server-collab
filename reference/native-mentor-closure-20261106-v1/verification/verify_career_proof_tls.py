"""Original owned career use -> teacher-specific proof mail -> quest consume."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
builder=W/'verify_quest_tls.py';tree=ast.parse(builder.read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
helpers=cases[:cases.index('            await accept(teacher,45002)')]
extra=r'''
            from els_server.storage import mentor_career_rewards as proof_store
            from els_server.protocol import mail_attachment_messages
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=35,revision=revision+1 WHERE uid=?',(uid[1],))
                grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)
                    for t in(214430,217920)],uid[1])
            await accept(teacher,45003);await accept(teacher,45004)
            await student.query(0x213,struct.pack('>i',0));await barrier(student)
            def dump():
                with closing(sqlite3.connect(cfg.state_file))as db:return [row for row in db.iterdump()if '"activity518_'not in row]
            baseline=read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')
            for stage,template,proof_template in((1,214430,189802),(2,217920,189803)):
                item=read('SELECT uid FROM inventory_items WHERE owner=?AND template=?',(uid[1],template))[0][0]
                body=struct.pack('>QQiiIB',item,0,0,0,0,0)
                before=dump()
                with patch.object(mail_attachment_messages,'detail',side_effect=ValueError('Owned late mentor proof mail encoding failure')):
                    failed=await student.query(0x219,body);assert failed.payload[:4]!=bytes(4)
                current=dump()
                assert current==before,{'removed':[line[:180]for line in before if line not in current][:8],
                    'added':[line[:180]for line in current if line not in before][:8]}
                success=await student.query(0x219,body);assert success.payload[:4]==bytes(4),success.payload[:4].hex()
                saved=read('SELECT teacher,mail_id FROM native_mentor_career_rewards WHERE student=?AND stage=?',(uid[1],stage))
                assert len(saved)==1 and saved[0][0]==uid[0]
                mid=saved[0][1];claim_mail=struct.pack('>IQ',1,mid)+bytes(6)
                assert(await student.query(0x1d2,struct.pack('>Q',mid))).payload[:4]!=bytes(4)
                assert(await outsider.query(0x1d4,claim_mail)).payload[:4]!=bytes(4)
                assert(await teacher.query(0x1d2,struct.pack('>Q',mid))).payload[:4]==bytes(4)
                assert(await teacher.query(0x1d4,claim_mail)).payload[:4]==bytes(4)
                assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=?',(uid[0],proof_template))==[(1,)]
                await teacher.query(0x1d4,claim_mail)
                failed=await student.query(0x219,body);assert failed.payload[:4]!=bytes(4)
                assert read('SELECT COUNT(*)FROM native_mentor_career_rewards WHERE student=?AND stage=?',(uid[1],stage))==[(1,)]
                assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=?',(uid[0],proof_template))==[(1,)]
                if stage==1:
                    await claim(teacher,45003)
                    assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=710097',(uid[0],))==[(1,)]
                    assert read('SELECT uid FROM inventory_items WHERE owner=?AND template=189802',(uid[0],))==[]
                    from els_server.domain.normal_fatigue_rules import potions
                    potion=read('SELECT uid FROM inventory_items WHERE owner=?AND template=710097',(uid[0],))[0][0]
                    with closing(sqlite3.connect(cfg.state_file))as db,db:
                        db.execute('UPDATE normal_fatigue_state SET current=0,revision=revision+1 WHERE owner=?',(uid[0],))
                    used=await teacher.query(0x196,struct.pack('>QBBBIi',potion,0,0,0,0,0));assert used.payload[:4]==bytes(4)
                    assert read('SELECT current FROM normal_fatigue_state WHERE owner=?',(uid[0],))==[(potions()[710097]['restore'],)]
                    assert not read('SELECT uid FROM inventory_items WHERE uid=?',(potion,))
            report['checks'].append('Real219 first/second career uses each create one teacher-owned proof mail; late mail encoder failure rolls back class, source debit and all mail rows; wrong characters cannot claim and retries add nothing')
            report['checks'].append('Actual45003 collection claim consumes189802 and grants one710097, then native196 consumes it and restores its original fatigue amount; second-job189803 remains exactly one toward the original three-proof45004 objective')
            await teacher.close();peers.remove(teacher)
            deadline=time.monotonic()+5
            while app.playing.get(values[0]['account_id'])is sessions[0]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            alt_uid=Characters(cfg.state_file,values[0]['account_id']).create('ProofAlt',1,'owned-proof-alt')['uid']
            LocalState(cfg.state_file,alt_uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            alternate=await connect(dict(values[0],uid=alt_uid),peers)
            assert(await alternate.query(0x1d2,struct.pack('>Q',mid))).payload[:4]!=bytes(4)
            assert(await alternate.query(0x1d4,claim_mail)).payload[:4]!=bytes(4)
            await alternate.close();peers.remove(alternate)
            deadline=time.monotonic()+5
            while app.playing.get(values[0]['account_id'])is not None:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            teacher=await connect(values[0],peers);sessions[0]=app.playing[values[0]['account_id']]
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=189803',(uid[0],))==[(1,)]
            assert read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')[:3]==baseline
            report['checks'].append('Same-account teacher alt cannot read or claim; original teacher authenticated restore retains one second-job proof; no ED or EXP rewards are introduced')
'''
foundation=W/'verify_relation_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main');source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
source=(source[:begin]+helpers+extra+source[end:]).replace("'relation-tls-'","'career-proof-tls-'")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);exec(compile(prefix,str(foundation),'exec'),globals())
generated=W/'generated-career-proof-main.py';generated.write_text(source+'\n','utf8');exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
