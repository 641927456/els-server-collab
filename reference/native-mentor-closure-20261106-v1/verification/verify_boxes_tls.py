"""Approved draw boundaries plus real owned TLS box use and fixed counters."""
from pathlib import Path
import ast,hashlib
W=Path(__file__).resolve().parent
builder=W/'verify_quest_tls.py';tree=ast.parse(builder.read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
helpers=cases[:cases.index('            await accept(teacher,45002)')]
extra=r'''
            from collections import Counter
            from els_server.domain.mentor_boxes import entries
            from els_server.domain.regional_boss_cubes import draw
            from els_server.storage import fixed_cubes
            from els_server.domain.tenebros_capacity_flow import selected
            row=next(r for r in entries()if r['template']==132812)
            rolls=Counter(draw(row,r)['template']for r in range(10000))
            assert rolls=={t:2000 for t in(132198,132202,132203,132204,132205)}
            for bad in(-1,10000,True):
                try:draw(row,bad)
                except ValueError:pass
                else:raise AssertionError('Out of domain draw accepted')
            await accept(student,45039);await fixture('duel','owned-box-three-source',3);await claim(student,45039)
            preview=await student.query(0x559,struct.pack('>iIBB',132812,0,0,0))
            assert preview.payload[:8]==struct.pack('>ii',0,132812)
            assert struct.unpack_from('>I',preview.payload,17)[0]==5
            box=read('SELECT uid FROM inventory_items WHERE owner=?AND template=132812',(uid[1],))[0][0]
            payload=struct.pack('>QBBBIi',box,0,0,0,0,0)
            original_open=fixed_cubes.open_cube
            for roll,template in zip((0,2000,4000,6000,9999),(132198,132202,132203,132204,132205)):
                def forced(*args,**kwargs):return original_open(*args,**kwargs,randbelow=lambda bound:roll)
                with patch.object(fixed_cubes,'open_cube',side_effect=forced):
                    answer=await student.query(0x196,payload);assert answer.payload[:4]==bytes(4),answer.payload[:4].hex()
                assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=?',(uid[1],template))==[(1,)]
            assert read('SELECT count FROM inventory_items WHERE uid=?',(box,))==[(5,)]
            operation=read('SELECT operation_id FROM inventory_action_receipts WHERE owner=?AND kind=406 ORDER BY rowid DESC LIMIT 1',(uid[1],))[0][0]
            before=read('SELECT *FROM inventory_items ORDER BY uid')
            def replay():
                path,owner,account,guard=selected(sessions[1])
                return original_open(path,owner,132812,payload,operation,account_id=account,prepare=guard)
            await app.call(replay)
            assert read('SELECT *FROM inventory_items ORDER BY uid')==before
            report['checks'].append('All10000 draw values select exactly2000 each; original559 preview lists five; five real196 uses consume exactly five boxes and grant each approved stone; exact operation replay adds nothing')
            def dump():
                with closing(sqlite3.connect(cfg.state_file))as db:return list(db.iterdump())
            before=dump()
            with patch.object(fixed_cubes,'result',side_effect=ValueError('Owned late box response failure')):
                failed=await student.query(0x196,payload);assert failed.payload[:4]!=bytes(4)
            assert dump()==before
            bad=await outsider.query(0x196,payload);assert bad.payload[:4]!=bytes(4)
            bad=await student.query(0x196,struct.pack('>QBBBIii',box,0,0,0,1,132193,0));assert bad.payload[:4]!=bytes(4)
            assert dump()==before
            report['checks'].append('Foreign actor, forged selection and late result encoding failure cannot debit or grant; exact SQL state is unchanged')
            for level,qid,dungeon,target,template,gain in((35,45033,30242,4,132840,10),(55,45035,33122,6,90000746,20)):
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=?',(level,uid[1]))
                await accept(student,qid);await fixture('clear','owned-fixed-box:'+str(qid),target,dungeon);await claim(student,qid)
                item=read('SELECT uid FROM inventory_items WHERE owner=?AND template=?',(uid[1],template))[0][0]
                preview=await student.query(0x559,struct.pack('>iIBB',template,0,0,0));assert preview.payload[:4]==bytes(4)
                body=struct.pack('>QBBBIi',item,0,0,0,0,0)
                captured=[]
                def diagnose(*args,**kwargs):
                    try:return original_open(*args,**kwargs)
                    except ValueError as error:captured.append(str(error));raise
                with patch.object(fixed_cubes,'open_cube',side_effect=diagnose):answer=await student.query(0x196,body)
                assert answer.payload[:4]==bytes(4),(template,answer.payload[:4].hex(),captured)
                current=10 if gain==10 else 30
                assert struct.unpack_from('>i',answer.payload,4)[0]==current
                assert read('SELECT count FROM known_resurrection_stones WHERE owner=?',(uid[1],))==[(current,)]
                assert read('SELECT uid FROM inventory_items WHERE uid=?',(item,))==[]
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            student=await connect(values[1],peers);sessions[1]=app.playing[values[1]['account_id']]
            assert read('SELECT count FROM known_resurrection_stones WHERE owner=?',(uid[1],))==[(30,)]
            assert read('SELECT count FROM inventory_items WHERE uid=?',(box,))==[(5,)]
            report['checks'].append('Actual earned132840/90000746 use the existing known resurrection counter and original197 count field:10 then30; both source boxes disappear and authenticated cold restore retains30')
'''
foundation=W/'verify_relation_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
source=source[:begin]+helpers+extra+source[end:]
source=source.replace("'relation-tls-'","'boxes-tls-'")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);exec(compile(prefix,str(foundation),'exec'),globals())
generated=W/'generated-boxes-main.py';generated.write_text(source+'\n','utf8')
exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
