"""Reuse the passed isolated TLS setup for distinct search/timeout/passive-peer edges."""
from pathlib import Path
import ast,hashlib

foundation=Path(__file__).with_name('verify_relation_tls.py')
original=foundation.read_text('utf8')
tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
assert source.count(anchor)==1
begin=source.index(anchor)
end=source.index("            report['ok']=True",begin)
cases=r'''
            def search_row():return read('SELECT owner,next_at FROM native_mentor_search_times ORDER BY owner')
            def search_receipts():return read('SELECT operation FROM native_mentor_operations WHERE kind=1812 ORDER BY operation')
            start=len(teacher.received)
            initial=await student.query(0x714)
            assert initial.payload==bytes(4)
            notice=await after(teacher,0x716,start)
            with closing(sqlite3.connect(cfg.state_file))as db:
                expected=wire.search_notice(storage.character(db,uid=uid[1])).payload
            assert notice.payload==expected
            old=search_row();receipts=search_receipts()
            denied=await student.query(0x714)
            assert struct.unpack('>i',denied.payload)[0]==1959 and search_row()==old and search_receipts()==receipts
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            student=await connect(values[1],peers);sessions[1]=app.playing[values[1]['account_id']]
            denied=await student.query(0x714)
            assert struct.unpack('>i',denied.payload)[0]==1959 and search_row()==old
            report['checks'].append('Actual714/715/716 broadcast matches native fields; repeated and authenticated cold reconnect requests retain the original60s cooldown')
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE native_mentor_search_times SET next_at=? WHERE owner=?',(int(time.time())-1,uid[1]))
            before=search_row()
            with patch.object(wire,'search_notice',side_effect=ValueError('Owned late search packet encoding failure')):
                failed=await student.query(0x714)
                assert struct.unpack('>i',failed.payload)[0]!=0
            assert search_row()==before and search_receipts()==receipts
            assert (await student.query(0x714)).payload==bytes(4) and len(search_receipts())==2
            report['checks'].append('Explicit elapsed-cooldown fixture: late716 encoder failure rolls back the new deadline/receipt; the next normal request succeeds')
            await invite();start=len(teacher.received)
            def expire_owned():
                pending=app.world.mentors.pending[sessions[1]]
                pending.expires=time.monotonic()-1
                app.world.mentors.expire()
            await app.call(expire_owned)
            expired=await after(teacher,0x1eb,start)
            assert expired.payload[-5:]==b'\0'+struct.pack('>i',1960) and not app.world.mentors.pending and not mentors()
            await invite();accepted,starts=await answer()
            assert accepted.payload[-5]==1
            await after(teacher,0x1eb,starts[0])
            assert len(mentors())==2
            # The inviter has received peer packets but has not sent another
            # mentor-sync trigger; its old own signature still has no relation.
            assert sessions[0].mentor_presence_signature[4]is None
            start=len(student.received);await teacher.close();peers.remove(teacher)
            deadline=time.monotonic()+5
            while app.playing.get(values[0]['account_id'])is sessions[0]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            await barrier(student)
            offline=await after(student,0x1e7,start)
            with closing(sqlite3.connect(cfg.state_file))as db:
                saved=storage.relation(db,uid[1]);expected=wire.partner(storage.public_info(db,uid[0],None,saved=saved)).payload
            offline=next((e for e in student.received[start:]if e.kind==0x1e7 and e.payload==expected),offline)
            for _ in range(10):
                if offline.payload==expected:break
                offline=await student.until(0x1e7)
            assert offline.payload==expected
            report['checks'].append('Explicit expired invitation returns native1960 and frees both sides; passive inviter logout projects offline even before its own signature refreshes')
            from els_server.storage.character_selection import save as save_selection
            from els_server.storage import character_lifecycle as lifecycle
            save_selection(cfg.state_file,values[0]['account_id'],[0]*5,[uid[0]])
            future=int(time.time())+3*lifecycle.DAY+1
            with patch.object(lifecycle,'current_time',return_value=future):
                scheduled=lifecycle.change(cfg.state_file,values[0]['account_id'],uid[0],'schedule')
            with patch.object(lifecycle,'current_time',return_value=scheduled['until']):
                lifecycle.change(cfg.state_file,values[0]['account_id'],uid[0],'finalize')
            start=len(student.received)
            await app.call(lambda:app.world.mentors.reconcile(app))
            await barrier(student)
            removed=await after(student,0x1e6,start)
            assert struct.unpack_from('>Q',removed.payload)[0]==uid[0] and not mentors()
            assert read('SELECT uid FROM characters WHERE uid=?',(uid[0],))==[(uid[0],)]
            with closing(sqlite3.connect(cfg.state_file))as db:assert not storage.exists(db,'native_mentor_graduations')
            report['checks'].append('Actual schedule/finalize API with explicit elapsed-time fixture; world reconciliation delivers native1E6 to the online counterpart, keeps tombstone data and creates no graduation reward')
'''
source=source[:begin]+cases+source[end:]
source=source.replace("'relation-tls-'","'relation-edges-tls-'")
source=source.replace('    app=server=None;peers=[];events=[]',
    '    report["foundation_sha256"]=FOUNDATION_SHA\n    app=server=None;peers=[];events=[]')
prefix='\n'.join(original.splitlines()[:node.lineno-1])
FOUNDATION_SHA=hashlib.sha256(foundation.read_bytes()).hexdigest()
exec(compile(prefix,str(foundation),'exec'),globals())
generated=Path(__file__).with_name('generated-relation-edges-main.py')
generated.write_text(source+'\n','utf8')
exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
