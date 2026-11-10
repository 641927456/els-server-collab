"""Original shared multi-stage PVE clear and random mission -> mentor counters."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
tree=ast.parse((W/'verify_party_play_tls.py').read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
cases=cases[:cases.index('            room=app.world.dungeons.room')]
cases=cases.replace('mid=30072;','mid=30182;').replace('at15=data.thresholds[14]','at15=data.thresholds[21]').replace('level=15','level=22')
cases=cases.replace('at the native AdequateLevel upper boundary','inside the native AdequateLevel range')
at="            async def party_invite(target,identity):"
extra=r'''
            async def accept(peer,qid):
                result=await peer.query(0xee,struct.pack('>ii',qid,10025));assert result.payload==bytes(4),(qid,result.payload.hex())
            await accept(teacher,45001);await accept(student,45032);await accept(student,45037)
'''
cases=cases.replace(at,extra+at)
extra=r'''
            from els_server.domain import dungeon_flow,legacy_pve_exp as xp_rules,pve_economy_flow as pve
            from els_server.storage import random_missions
            from els_server.protocol.protocol_codec import Event
            room=app.world.dungeons.room(sessions[0]);offset=[0.]
            await app.call(lambda:[setattr(s.dungeon_run,'clock',lambda:time.monotonic()+offset[0])for s in sessions])
            report['explicit_native_HP_and_elapsed_gate_fixtures']=True
            def death(n):
                hp=struct.unpack('>I',struct.pack('>f',n['hp']))[0]
                return struct.pack('>iBQQ6fBI',n['key'],1,uid[0],uid[0],0,0,0,0,0,0,0,hp)+struct.pack('>IIQIQ',0,0,0,0,uid[0])
            def counts(qid):return json.loads(read('SELECT objectives FROM character_quests WHERE owner=?AND quest=?',(uid[0]if qid==45001 else uid[1],qid))[0][0])
            trace=[];failed=False
            # Draw0 is an explicit deterministic20%-hit fixture. All assignment,
            # death/transition/receipt and completion writers remain original.
            with patch.object(random_missions.secrets,'randbelow',return_value=0):
                for step in range(100):
                    if room.phase=='clear':break
                    run=sessions[0].dungeon_run
                    trace.append(dict(stage=run.stage,part=run.part,visits=run.visits,phase=room.phase))
                    report['trace']=trace
                    if not sessions[0].dungeon_substage_synced:
                        for peer in peers:await peer.send(0xb3,bytes(9));await barrier(peer)
                        assert all(s.dungeon_substage_synced for s in sessions)
                    targets=[n for n in run.current['npcs']if n['active']and n['key']not in run.defeated and xp_rules.eligible(n)]
                    for n in targets:
                        ack=await teacher.query(0xad,death(n),reply=0xae);assert ack.payload[:4]==bytes(4)
                    condition=struct.pack('>iiHI',run.native_stage,run.part,0,len(run.current['conditions']))+bytes([1])*len(run.current['conditions'])+b'\0'
                    await teacher.query(0x471,condition,reply=0x472)
                    offset[0]+=100
                    await app.call(lambda:[app.world.send(s,e)for s in sessions for e in dungeon_flow.periodic(s)])
                    await app.call(lambda:app.world.dungeons.part_wait(room))
                    assert run.next is not None,(trace[-1],[(n['key'],n['template'],n['active'],n['key']in run.defeated,xp_rules.eligible(n))for n in run.current['npcs']])
                    if run.next['kind']==0:
                        for peer in peers:await peer.query(0xb8,struct.pack('>b',run.next['part']),reply=0xb9)
                    assert room.phase=='part_end',(trace[-1],run.next)
                    body=struct.pack('>b',run.part)
                    for peer in peers[:2]:await peer.query(0xbb,body,reply=0xbc)
                    if run.next['kind']==4 and not failed:
                        before=read('SELECT *FROM character_quests WHERE quest IN(45001,45032,45037)ORDER BY owner,quest')
                        old=quest_messages.progress
                        def fail_tasks(rows):
                            if any(row['id']in(45001,45032,45037)for row in rows):raise ValueError('Owned late final mentorF3 encoding failure')
                            return old(rows)
                        with patch.object(quest_messages,'progress',side_effect=fail_tasks):
                            await outsider.send(0xbb,body);await barrier(outsider)
                        assert read('SELECT *FROM character_quests WHERE quest IN(45001,45032,45037)ORDER BY owner,quest')==before
                        assert not any(s.clear_notified for s in sessions)
                        failed=True
                    await outsider.query(0xbb,body,reply=0xbc)
                    for peer in peers:await barrier(peer)
                else:raise AssertionError('Original graph did not finish')
            assert failed and room.phase=='clear'
            levels=read('SELECT uid,level FROM characters ORDER BY uid')
            assert levels[1][1]>22,levels
            report['actual_level_up_during_shared_run']=levels
            assert counts(45001)=={'45001':1},counts(45001)
            assert counts(45032)=={'45032':1},counts(45032)
            assert counts(45037)=={'45037':1},counts(45037)
            assert read('SELECT owner,found,completed FROM random_mission_runs ORDER BY owner')==[(who,1,1)for who in uid]
            before=read('SELECT *FROM character_quests WHERE quest IN(45001,45032,45037)ORDER BY owner,quest')
            await outsider.query(0xbb,body,reply=0xbc)
            assert read('SELECT *FROM character_quests WHERE quest IN(45001,45032,45037)ORDER BY owner,quest')==before
            report['trace']=trace
            report['checks'].append('Real three-owner nativeAD/B8/BB/B3 multi-stage clear produces original reward and random-mission receipts, teacher appropriate-clear45001, student regional45032 and actual mission45037 each exactly1; duplicateBB never counts twice')
            report['checks'].append('Late mentorF3 final encoding failure rolls back clear/mission/task effects for all members and preserves native uncleared state; original finalBB retry succeeds')
'''
cases+=extra
foundation=W/'verify_relation_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main');source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
source=(source[:begin]+cases+source[end:]).replace("'relation-tls-'","'clear-tasks-tls-'")
source=source.replace("index+1,'mentor-tls-'","(1 if index==1 else index+1),'mentor-tls-'")
source=source.replace("ServerConfig(mode='friends',host=","ServerConfig(mode='friends',friends_coop_enabled=True,host=")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);exec(compile(prefix,str(foundation),'exec'),globals())
generated=W/'generated-clear-tasks-main.py';generated.write_text(source+'\n','utf8');exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
