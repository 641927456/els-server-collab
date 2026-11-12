"""Actual mentor quest packets/claims; explicit private activity fixtures."""
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
            from els_server.domain import mentor_quests as task_rules,quest_flow
            from els_server.storage import mentor_quests as tasks
            await invite();accepted,starts=await answer();assert accepted.payload[-5]==1
            await after(teacher,0x1eb,starts[0])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=15,revision=revision+1 WHERE uid=?',(uid[1],))
            async def accept(peer,qid):
                result=await peer.query(0xee,struct.pack('>ii',qid,10025));assert result.payload==bytes(4),(qid,result.payload.hex())
                await barrier(peer)
            def claim_body(qid):return struct.pack('>iiI5B',qid,0,0,0,0,0,0,0)
            async def claim(peer,qid):
                result=await peer.query(0xf4,claim_body(qid));assert result.payload[:4]==bytes(4),(qid,result.payload[:4].hex())
            def counts(owner,qid):
                return json.loads(read('SELECT objectives FROM character_quests WHERE owner=?AND quest=?',(owner,qid))[0][0])
            def fixture(kind,operation,n=1,dungeon=30072):
                # Explicit activity fixture only: actual sealed producers are
                # qualified separately. This does not claim a natural battle.
                def run():
                    deliveries=[]
                    with closing(sqlite3.connect(cfg.state_file))as db,db:
                        db.execute('BEGIN IMMEDIATE')
                        saved=storage.relation(db,uid[1]);char=storage.character(db,uid=uid[1])
                        fact=dict(teacher=uid[0],student=uid[1],generation=saved['generation'],
                            teacher_class=career,student_class=char['unit_class'],student_level=char['level'],
                            xp_percent=50,fatigue_free=True)
                        activity=dict(kind=kind,dungeon=dungeon,winner=uid[1],boss_witness=True)
                        for index in range(n):
                            for peer in sessions[:2]:
                                messages=tasks.record(db,peer.account.uid,operation+':'+str(index),fact,activity,lambda writer:True)
                                deliveries.append((peer,messages))
                    for peer,messages in deliveries:
                        for message in messages:app.world.send(peer,message)
                return app.call(run)
            await accept(teacher,45002);await accept(student,45039);await accept(student,45040);await accept(student,45031)
            baseline=read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')
            await fixture('duel','owned-task-first-three',3)
            await barrier(student);await barrier(teacher)
            assert counts(uid[0],45002)=={'45002':3} and counts(uid[1],45039)=={'45039':3}
            assert counts(uid[1],45040)=={'45040':1}
            await claim(teacher,45002);await claim(student,45039);await claim(student,45040)
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=132812',(uid[1],))==[(10,)]
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=166572',(uid[1],))==[(1,)]
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=189800',(uid[0],))==[(1,)]
            await claim(teacher,45002)
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=189800',(uid[0],))==[(1,)]
            old_operation=read('SELECT operation FROM native_mentor_quest_operations WHERE owner=?AND quest=45002 AND kind=?ORDER BY rowid LIMIT 1',(uid[0],'claim'))[0][0]
            report['explicit_activity_fixtures']=True
            report['checks'].append('OriginalEE/F0/F3/F4/F5 task path; explicit three-duel source fixtures grant one189800, ten132812 and one166572; duplicate claim never adds another reward')
            await accept(teacher,45002)
            assert counts(uid[0],45002)=={'45002':0}
            before=read('SELECT *FROM native_mentor_quest_cycles')
            try:
                await app.call(lambda:quest_flow.store(sessions[0]).action('claim',quest_messages.request(0xf4,claim_body(45002)),old_operation,lambda r:[]))
            except ValueError:pass
            else:raise AssertionError('Old cycle claim was accepted into the new cycle')
            assert read('SELECT *FROM native_mentor_quest_cycles')==before
            await fixture('duel','owned-task-second-three',3)
            def dump():
                with closing(sqlite3.connect(cfg.state_file))as db:return list(db.iterdump())
            before=dump()
            original_ack=quest_messages.reward_ack
            def fail_success(*args,**kwargs):
                if kwargs.get('result',0)==0:raise ValueError('Owned lateF5 encoding failure')
                return original_ack(*args,**kwargs)
            with patch.object(quest_messages,'reward_ack',side_effect=fail_success):
                failed=await teacher.query(0xf4,claim_body(45002));assert failed.payload[:4]!=bytes(4)
            assert dump()==before
            await claim(teacher,45002)
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=189800',(uid[0],))==[(2,)]
            assert len(read('SELECT *FROM native_mentor_quest_history WHERE owner=?AND quest=45002',(uid[0],)))==1
            report['checks'].append('Teacher repeats in a fresh generation; old operation cannot claim across cycles; lateF5 encoder failure rolls back item allocation, source, completion and action receipt; normal retry succeeds')
            await fixture('clear','owned-task-two-clears',2)
            await claim(student,45031)
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=710001',(uid[1],))==[(10,)]
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=20,revision=revision+1 WHERE uid=?',(uid[1],))
            await accept(student,45037)
            await fixture('random','owned-task-twenty-missions',20)
            await claim(student,45037)
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=710097',(uid[1],))==[(10,)]
            from els_server.domain.acquisition_policy import can_acquire
            assert not can_acquire(710097) and not can_acquire(132812)
            assert read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')==baseline
            report['checks'].append('Explicit clear/random mission fixtures use current native region sets and levels; actual claims give ten recovery potions and ten fatigue potions; new generic grants stay closed and ED/EXP stay unchanged')
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            student=await connect(values[1],peers);sessions[1]=app.playing[values[1]['account_id']]
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=710097',(uid[1],))==[(10,)]
            assert len(read('SELECT *FROM completed_quests WHERE owner=?AND quest IN(45031,45037,45039,45040)',(uid[1],)))==4
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid[1],))
            failed=await student.query(0xee,struct.pack('>ii',45038,10025));assert failed.payload!=bytes(4)
            report['checks'].append('Authenticated cold restore retains claimed items and one-time completions; level99 cannot start another student task')
'''
source=source[:begin]+cases+source[end:]
source=source.replace("'relation-tls-'","'quest-tls-'")
source=source.replace('    app=server=None;peers=[];events=[]',
    '    report["foundation_sha256"]=FOUNDATION_SHA\n    app=server=None;peers=[];events=[]')
source=source.replace("except BaseException:report['error']=traceback.format_exc()",
    "except BaseException:\n            report['error']=traceback.format_exc()\n            report['failure_events']=[{k:row[k]for k in('event','error','reason','detail')if k in row}for row in events[-20:]]")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);FOUNDATION_SHA=hashlib.sha256(foundation.read_bytes()).hexdigest()
exec(compile(prefix,str(foundation),'exec'),globals())
generated=Path(__file__).with_name('generated-quest-main.py');generated.write_text(source+'\n','utf8')
exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
