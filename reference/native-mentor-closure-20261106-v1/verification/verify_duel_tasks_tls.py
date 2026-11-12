"""Actual native challenge requests produce only the bound pair's tasks."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
builder=W/'verify_quest_tls.py';tree=ast.parse(builder.read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
helpers=cases[:cases.index('            await accept(teacher,45002)')]
extra=r'''
            from combined_qa_client import action
            from els_server.protocol.local_messages import wstring as ws
            pvp=app.world.pvp;witness=object()
            await app.call(lambda:pvp.support.update({s.account.account_id:(witness,'owned-fixture','owned-fixture',True)for s in sessions}))
            await accept(teacher,45002);await accept(student,45039);await accept(student,45040)
            baseline=read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')
            async def battle(left,right,*,rollback=False):
                first,second=peers[left],peers[right]
                body=struct.pack('>QIQI',uid[left],0,uid[right],0)+ws(values[left]['character_name'])+struct.pack('>IBi',0,0,0)
                incoming_start=len(second.received)
                ack=await first.query(0x5c6,body);assert ack.payload[:4]==bytes(4),ack.payload[:4].hex()
                incoming=await after(second,0x5c8,incoming_start)
                offset=28+struct.unpack_from('>I',incoming.payload,24)[0]
                full=incoming.payload[offset:-5]
                starts=[len(first.received),len(second.received)]
                await second.send(0x5c9,struct.pack('>QQi',uid[left],uid[right],0)+full+bytes(8))
                for peer,start in zip((first,second),starts):await after(peer,0x34b,start)
                room=pvp.room(sessions[left]);assert room.kind=='challenge'
                starts=[len(first.received),len(second.received)]
                for peer in(first,second):await action(peer,0x91,struct.pack('>iI',100,0))
                for peer,start in zip((first,second),starts):await after(peer,0x96,start)
                await action(first,0xa7,struct.pack('>iQQBffi?',-1,uid[right],uid[right],0,0.,0.,-1,False))
                starts=[len(first.received),len(second.received)];await first.send(0xaa)
                for peer,start in zip((first,second),starts):await after(peer,0x9d,start)
                starts=[len(first.received),len(second.received)]
                await action(first,0x9e,struct.pack('>f',0.)+bytes(178))
                if rollback:
                    before=read('SELECT *FROM character_quests WHERE quest IN(45002,45039,45040)ORDER BY owner,quest')
                    with patch.object(quest_messages,'progress',side_effect=ValueError('Owned late duel F3 encoding failure')):
                        await second.send(0x9e,struct.pack('>f',23456.)+bytes(178));await barrier(second)
                    assert read('SELECT *FROM character_quests WHERE quest IN(45002,45039,45040)ORDER BY owner,quest')==before
                    assert room.phase=='reporting'
                await action(second,0x9e,struct.pack('>f',23456.)+bytes(178))
                for peer,start in zip((first,second),starts):await after(peer,0xc2,start)
                assert room.phase=='result'
                saved=read('SELECT *FROM character_quests WHERE quest IN(45002,45039,45040)ORDER BY owner,quest')
                await action(second,0x9e,struct.pack('>f',23456.)+bytes(178))
                assert read('SELECT *FROM character_quests WHERE quest IN(45002,45039,45040)ORDER BY owner,quest')==saved
                for peer in(first,second):
                    await action(peer,0x225,struct.pack('>iB',20001,0))
                    await action(peer,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
                assert not pvp.duels.returning
            await battle(0,2)
            assert counts(uid[0],45002)=={'45002':0}and counts(uid[1],45039)=={'45039':0}
            report['checks'].append('Real unrelated-opponent challenge finishes without advancing either mentor task')
            for index in range(3):await battle(0,1,rollback=index==0)
            assert counts(uid[0],45002)=={'45002':3}and counts(uid[1],45039)=={'45039':3}and counts(uid[1],45040)=={'45040':1}
            assert read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')==baseline
            report['checks'].append('Actual5C6/5C9/34B/91/A7/AA/9E/C2 and Town returns complete three teacher/student rounds; one student win, no ED/EXP; repeated result never counts twice; late F3 failure rolls back task counters and retries')
            await claim(teacher,45002);await claim(student,45039);await claim(student,45040)
            assert read('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=132812',(uid[1],))==[(10,)]
            report['checks'].append('The actual sealed challenge counters qualify nativeF4 claims, including ten approved stone boxes')
            from els_server.storage import fixed_cubes
            box=read('SELECT uid FROM inventory_items WHERE owner=?AND template=166572',(uid[1],))[0][0]
            preview=await student.query(0x559,struct.pack('>iIBB',166572,0,0,0));assert preview.payload[:4]==bytes(4)
            assert struct.unpack_from('>I',preview.payload,17)[0]==4
            body=struct.pack('>QBBBIi',box,0,0,0,0,0)
            before=read('SELECT *FROM inventory_items ORDER BY uid')
            with patch.object(fixed_cubes,'result',side_effect=ValueError('Owned late accessory result encoding failure')):
                failed=await student.query(0x196,body);assert failed.payload[:4]!=bytes(4)
            assert read('SELECT *FROM inventory_items ORDER BY uid')==before
            opened=await student.query(0x196,body);assert opened.payload[:4]==bytes(4),opened.payload[:4].hex()
            expected={188888,188889,188890,188891}
            rows=read('SELECT i.template,i.count,e.expires_at FROM inventory_items i JOIN item_expiration e ON e.item_uid=i.uid WHERE i.owner=?AND i.template BETWEEN 188888 AND 188891',(uid[1],))
            assert {r[0]for r in rows}==expected and all(r[1]==1 and abs(r[2]-int(time.time())-7*86400)<=3 for r in rows),rows
            assert read('SELECT uid FROM inventory_items WHERE uid=?',(box,))==[]
            report['checks'].append('Actually earned166572 previews and opens the current Aisha four-piece set; each item lasts7days; late result failure preserves the source and all outputs')
            from els_server.domain.ordinary_accessories import definitions as accessories
            from els_server.domain.acquisition_policy import can_acquire
            for template in expected:
                assert not can_acquire(template)
                item=read('SELECT uid,slot FROM inventory_items WHERE owner=?AND template=?',(uid[1],template))[0]
                slot=accessories()[template]['main_slots'][0]
                ack=await student.query(0x104,struct.pack('>BiBiB',2,item[1],9,slot,0));assert ack.payload[-4:]==bytes(4),(template,ack.payload[-4:].hex(),sessions[1]._wear_rejection)
                assert read('SELECT bag_group,slot FROM inventory_items WHERE uid=?',(item[0],))==[(9,slot)]
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            student=await connect(values[1],peers);sessions[1]=app.playing[values[1]['account_id']]
            current=read('SELECT template,bag_group,slot FROM inventory_items WHERE owner=?AND template BETWEEN 188888 AND 188891',(uid[1],))
            assert {r[0]for r in current if r[1]==9}>=expected,current
            report['checks'].append('All four actual accessories equip through original104/105 and persist across authenticated cold restore; generic new acquisition of these compatibility items remains closed')
'''
foundation=W/'verify_relation_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main');source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
source=(source[:begin]+helpers+extra+source[end:]).replace("'relation-tls-'","'duel-tasks-tls-'")
source=source.replace("ServerConfig(mode='friends',host=","ServerConfig(mode='friends',normal_equipment_moves_enabled=True,host=")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);exec(compile(prefix,str(foundation),'exec'),globals())
generated=W/'generated-duel-tasks-main.py';generated.write_text(source+'\n','utf8');exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
