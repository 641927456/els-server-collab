"""Real shared Black Gate admission and accepted1367 death, no synthetic clears."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
tree=ast.parse((W/'verify_party_play_tls.py').read_text('utf8'))
cases=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
cases=cases[:cases.index("            with patch('els_server.domain.hot_time.unlimited_fatigue'")]
cases=cases.replace('mid=30072;','mid=38300;').replace('at15=data.thresholds[14]','at15=data.thresholds[69]').replace('level=15','level=70')
begin=cases.index("                db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None")
end=cases.index("            report['explicit_level",begin)
cases=cases[:begin]+cases[end:]
at='            async def party_invite(target,identity):'
cases=cases.replace(at,r'''
            accepted=await student.query(0xee,struct.pack('>ii',45038,10025));assert accepted.payload==bytes(4),accepted.payload.hex()
'''+at)
cases+=r'''
            for peer,value in zip(peers[1:],values[1:]):
                await peer.send(0x14c,b'\1'+bytes(4))
                while struct.unpack_from('>Q',(await peer.until(0x14d)).payload,4)[0]!=value['uid']:pass
            preflight=await teacher.query(0x7d4,struct.pack('>ii',1,mid));assert preflight.payload[:4]==bytes(4),preflight.payload[:4].hex()
            entry=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
            await teacher.send(0x382,entry);assert(await teacher.until(0x383)).payload[:4]==bytes(4)
            for peer in peers:await peer.until(0x14a)
            for peer in peers:await peer.send(0x91,struct.pack('>ii',100,0));await peer.until(0x92)
            for peer in peers:await peer.until(0xb2)
            for peer in peers:await peer.send(0xb3,bytes(9));await peer.until(0xb4)
            for peer in peers:await peer.until(0xbd);await barrier(peer)
            room=app.world.dungeons.room(sessions[0]);assert room.identity==38300 and room.phase=='active'
            def counts():return json.loads(read('SELECT objectives FROM character_quests WHERE owner=?AND quest=45038',(uid[1],))[0][0])
            assert counts()=={'45038':0}
            run=sessions[0].dungeon_run;boss=next(n for n in run.current['npcs']if n['template']==1367)
            hp=struct.unpack('>I',struct.pack('>f',boss['hp']))[0]
            body=struct.pack('>iBQQ6fBI',boss['key'],1,uid[0],uid[0],0,0,0,0,0,0,0,hp)+struct.pack('>IIQIQ',0,0,0,0,uid[0])
            ack=await teacher.query(0xad,body,reply=0xae);assert ack.payload[:4]==bytes(4)
            for peer in peers:await barrier(peer)
            assert counts()=={'45038':1},counts()
            assert all(s.dungeon_run.defeated.get(boss['key'])==body for s in sessions)
            before=read('SELECT *FROM native_mentor_quest_facts ORDER BY operation,owner,kind')
            await teacher.query(0xad,body,reply=0xae)
            for peer in peers:await barrier(peer)
            assert counts()=={'45038':1}and read('SELECT *FROM native_mentor_quest_facts ORDER BY operation,owner,kind')==before
            report['checks'].append('Original three-owner Black Gate admission,91/B3 and acceptedAD of actual issued1367 produce student45038 exactly1; original inactive/allied1368 is never killed and no source actors/clear bits are forged; repeatAD does not recount')
'''
foundation=W/'verify_relation_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main');source=ast.get_source_segment(original,node)
anchor="            assert [struct.unpack('>i',next(e for e in reversed(p.received)if e.kind==0x717).payload)[0]for p in peers]==[0,1,1]\n"
begin=source.index(anchor);end=source.index("            report['ok']=True",begin)
source=(source[:begin]+cases+source[end:]).replace("'relation-tls-'","'black-gate-tasks-tls-'")
source=source.replace("index+1,'mentor-tls-'","(1 if index==1 else index+1),'mentor-tls-'")
source=source.replace("ServerConfig(mode='friends',host=","ServerConfig(mode='friends',friends_coop_enabled=True,host=")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);exec(compile(prefix,str(foundation),'exec'),globals())
generated=W/'generated-black-gate-tasks-main.py';generated.write_text(source+'\n','utf8');exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
