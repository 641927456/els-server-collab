"""Actual graduation letter, scoped claim, title use, cold restore and expiry."""
from pathlib import Path
import ast,hashlib
foundation=Path(__file__).with_name('verify_relation_tls.py')
original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
assert source.count(anchor)==1
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
cases=r'''
            await invite();accepted,starts=await answer();assert accepted.payload[-5]==1
            await after(teacher,0x1eb,starts[0])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE native_mentor_relations SET formed_at=?',(int(time.time())-storage.MIN_RELATION_SECONDS,))
                db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid[1],))
            assert (await student.query(0x1e4,struct.pack('>Q',uid[0]))).payload[:4]==bytes(4)
            mid=read('SELECT mail_id FROM native_mentor_graduations')[0][0]
            details=await student.query(0x1d2,struct.pack('>Q',mid));assert details.payload[:4]==bytes(4)
            assert (await teacher.query(0x1d2,struct.pack('>Q',mid))).payload[:4]!=bytes(4)
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            alt_uid=Characters(cfg.state_file,values[1]['account_id']).create('MentorAlt',2,'owned-mentor-alt')['uid']
            LocalState(cfg.state_file,alt_uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            alternate=await connect(dict(values[1],uid=alt_uid),peers)
            claim=struct.pack('>IQ',1,mid)+bytes(6)
            assert (await alternate.query(0x1d2,struct.pack('>Q',mid))).payload[:4]!=bytes(4)
            assert (await alternate.query(0x1d4,claim)).payload[:4]!=bytes(4)
            await alternate.close();peers.remove(alternate)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is not None:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            student=await connect(values[1],peers);sessions[1]=app.playing[values[1]['account_id']]
            assert (await student.query(0x1d4,claim)).payload[:4]==bytes(4)
            token=read('SELECT uid,count FROM inventory_items WHERE owner=?AND template=189801',(uid[1],))
            assert len(token)==1 and token[0][1]==1
            assert (await student.query(0x1d4,claim)).payload[:4]==bytes(4)
            assert read('SELECT uid,count FROM inventory_items WHERE owner=?AND template=189801',(uid[1],))==token
            report['checks'].append('Actual graduation issues one189801 escrow; original read/claim works only for the student character, rejects teacher and same-account alt, and repeat claim cannot duplicate it')
            use_body=struct.pack('>QQiiIB',token[0][0],0,0,0,0,0)
            used=await student.query(0x219,use_body)
            assert used.payload[:4]==bytes(4),used.payload.hex()
            assert not read('SELECT uid FROM inventory_items WHERE uid=?',(token[0][0],))
            row=read('SELECT scope,subject,acquired_at,expires_at FROM title_ownership WHERE title=45000')
            assert len(row)==1 and row[0][:2]==('character',uid[1]) and row[0][3]-row[0][2]==7*86400,row
            selected=await student.query(0x213,struct.pack('>i',45000));assert selected.payload[:4]==bytes(4)
            assert read('SELECT title FROM title_equipment WHERE owner=?',(uid[1],))==[(45000,)]
            second=await student.query(0x219,use_body);assert second.payload[:4]!=bytes(4)
            assert read('SELECT scope,subject,acquired_at,expires_at FROM title_ownership WHERE title=45000')==row
            report['checks'].append('Actual219 consumes the exact token once, creates character-owned title45000 for exactly604800s, and native213 equips it; reusing the consumed UID cannot extend its period')
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            student=await connect(values[1],peers);sessions[1]=app.playing[values[1]['account_id']]
            assert read('SELECT title FROM title_equipment WHERE owner=?',(uid[1],))==[(45000,)]
            from els_server.storage import titles,title_levels
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert titles.snapshot(db,uid[1],row[0][3]-1)['title']==45000
                assert titles.snapshot(db,uid[1],row[0][3])['title']==0
                assert all(r['title']!=45000 for r in titles.snapshot(db,alt_uid,row[0][2])['owned'])
            expired,notices=await app.call(lambda:title_levels.synchronize(cfg.state_file,uid[1],now=row[0][3]))
            assert expired['title']==0 and all(r['title']!=45000 for r in expired['owned'])
            for notice in notices:encode_event(notice)
            assert read('SELECT title FROM title_equipment WHERE owner=?',(uid[1],))==[(0,)]
            report['checks'].append('Authenticated cold restore retains the original expiry/selection; explicit future-clock boundary expires at exactly7days, removes its projection and clears the selected title through the existing synchronizer')
'''
source=source[:begin]+cases+source[end:]
source=source.replace("'relation-tls-'","'graduation-tls-'")
source=source.replace('    app=server=None;peers=[];events=[]',
    '    report["foundation_sha256"]=FOUNDATION_SHA\n    app=server=None;peers=[];events=[]')
source=source.replace("except BaseException:report['error']=traceback.format_exc()",
    "except BaseException:\n            report['error']=traceback.format_exc()\n            report['failure_events']=[{k:row[k]for k in('event','error','reason','detail')if k in row}for row in events[-20:]]")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);FOUNDATION_SHA=hashlib.sha256(foundation.read_bytes()).hexdigest()
exec(compile(prefix,str(foundation),'exec'),globals())
generated=Path(__file__).with_name('generated-graduation-main.py');generated.write_text(source+'\n','utf8')
exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
