"""Actual three-member party, admission/loading/death writers and mentor effects."""
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
            from els_server.protocol.local_messages import wstring
            from els_server.domain import mentor_play,normal_fatigue_flow as fatigue_flow
            from els_server.storage import normal_fatigue as fatigue
            from els_server.domain.region_quests import region_catalog
            from els_server.game_data import client_data
            await invite();accepted,starts=await answer();assert accepted.payload[-5]==1
            await after(teacher,0x1eb,starts[0])
            mid=30072;data=client_data();at15=data.thresholds[14]
            career=100  # Exact current parent10 -> second class100 branch.
            regions=region_catalog().data['dungeons'][str(mid)]
            required=sorted({region_catalog().data['regions'][str(r)]['requirement'].get('RequireQuestID')for r in regions if str(r)in region_catalog().data['regions']}-{0,None})
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET unit_class=?,revision=revision+1 WHERE uid=?',(career,uid[0]))
                db.execute('UPDATE characters SET level=15,unit_class=10,revision=revision+1 WHERE uid=?',(uid[1],))
                db.execute('UPDATE characters SET level=15,revision=revision+1 WHERE uid=?',(uid[2],))
                db.execute('UPDATE reward_balances SET experience=? WHERE uid IN(?,?)',(at15,uid[1],uid[2]))
                db.execute('UPDATE reward_balances SET experience=? WHERE uid=?',(data.thresholds[-1],uid[0]))
                db.executemany('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',[(who,q,1,'{}')for who in uid for q in required])
                db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
                for who,account in zip(uid,values):
                    fatigue._apply(db,cfg.state_file,who,account['account_id'],'owned-fatigue-empty:'+str(who),'stage',
                        dict(explicit_depleted_fixture=True,owner=who),'0'*64,4800,
                        prepare=lambda writer:fatigue._writer(writer,cfg.state_file))
            report['explicit_level_class_experience_admission_and_fatigue_fixtures']=True
            async def party_invite(target,identity):
                body=struct.pack('>Q',identity['uid'])+wstring(identity['character_name'])+struct.pack('>iBi',0,1,30000)+bytes(6)+wstring('')+bytes(15)
                assert (await teacher.query(0x136,body)).payload[:4]==bytes(4)
                await target.until(0x138)
                await target.send(0x139,struct.pack('>QQBiBQ',uid[0],identity['uid'],1,0,0,0))
                assert (await target.until(0x13a)).payload[:4]==bytes(4)
                await teacher.until(0x13b);await target.until(0x13b)
            await party_invite(student,values[1]);await party_invite(outsider,values[2])
            party=app.world.party_of[sessions[0]];assert tuple(party['members'])==tuple(sessions)
            assert (await teacher.query(0x145,struct.pack('>ibb',mid,0,0))).payload[:4]==bytes(4)
            with patch('els_server.domain.hot_time.unlimited_fatigue',return_value=False):
                admission=await app.call(lambda:[fatigue_flow.admission_result(s,mid)for s in sessions])
                assert admission[:2]==[0,0] and admission[2]!=0,admission
            report['checks'].append('Actual native three-person party; zero-fatigue mentor pair admitted at the native AdequateLevel upper boundary, unrelated zero-fatigue member denied')
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE normal_fatigue_state SET current=600,revision=revision+1 WHERE owner=?',(uid[2],))
            for peer,value in zip(peers[1:],values[1:]):
                await peer.send(0x14c,b'\1'+bytes(4))
                while struct.unpack_from('>Q',(await peer.until(0x14d)).payload,4)[0]!=value['uid']:pass
            with patch('els_server.domain.hot_time.unlimited_fatigue',return_value=False):
                preflight=await teacher.query(0x7d4,struct.pack('>ii',1,mid));assert preflight.payload[:4]==bytes(4),preflight.payload.hex()
                entry=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
                await teacher.send(0x382,entry);assert(await teacher.until(0x383)).payload[:4]==bytes(4)
                for peer in peers:await peer.until(0x14a)
                for peer in peers:await peer.send(0x91,struct.pack('>ii',100,0));await peer.until(0x92)
                for peer in peers:await peer.until(0xb2)
                before=read('SELECT *FROM normal_fatigue_state ORDER BY owner')
                for peer in peers[:2]:await peer.send(0xb3,bytes(9));await peer.until(0xb4)
                await barrier(teacher);assert read('SELECT *FROM normal_fatigue_state ORDER BY owner')==before
                original_apply=fatigue._apply
                def fail_last(db,path,owner,*args,**kwargs):
                    if owner==uid[2]:raise ValueError('Owned last member fatigue encoding failure')
                    return original_apply(db,path,owner,*args,**kwargs)
                with patch.object(fatigue,'_apply',fail_last):
                    await outsider.send(0xb3,bytes(9));await barrier(outsider)
                assert read('SELECT *FROM normal_fatigue_state ORDER BY owner')==before
                assert all(not s.dungeon_substage_synced for s in sessions)
                await outsider.send(0xb3,bytes(9));await outsider.until(0xb4)
                for peer in peers:await peer.until(0xbd);await barrier(peer)
            rows=read('SELECT owner,current FROM normal_fatigue_state ORDER BY owner')
            assert rows[0:2]==[(uid[0],0),(uid[1],0)] and 0<rows[2][1]<600,rows
            paid=rows[2][1]
            await teacher.query(0xb3,bytes(9),reply=0xb4)
            assert read('SELECT owner,current FROM normal_fatigue_state ORDER BY owner')==rows
            report['checks'].append('Real shared loaded barrier: late third-member failure rolls back all; retry leaves pair at0 and charges only outsider; repeatedB3 does not debit')
            room=app.world.dungeons.room(sessions[0])
            with closing(sqlite3.connect(cfg.state_file))as db:
                db.execute('BEGIN');facts=mentor_play.effects(db,tuple(sessions),room,mid)
            assert facts[uid[1]]['xp_percent']==100 and facts[uid[0]]['xp_percent']==0 and uid[2]not in facts
            assert mentor_play.percentages(career,2)==50 and mentor_play.percentages(career,11)==80
            assert mentor_play.percentages(career,1)==80 and mentor_play.percentages(career,10)==100
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=16 WHERE uid=?',(uid[1],))
                assert not mentor_play.effects(db,tuple(sessions),room,mid)[uid[0]]['fatigue_free']
                db.execute('UPDATE characters SET level=15 WHERE uid=?',(uid[1],))
            report['checks'].append('Current careers.PARENTS yields50/80/100 percent; only bound student receivesXP; AdequateLevel15 free and16 paid uses the existing original range rule')
            from els_server.domain import legacy_pve_exp as xp_rules,pve_economy_flow as pve
            from els_server.domain import dungeon_lifecycle
            from els_server.protocol.protocol_codec import Event
            def death(n):
                hp=struct.unpack('>I',struct.pack('>f',n['hp']))[0]
                body=struct.pack('>iBQQ6fBI',n['key'],1,uid[0],uid[0],0,0,0,0,0,0,0,hp)+struct.pack('>IIQIQ',0,0,0,0,uid[0])
                return Event(0x202,performers=(0,),kind=0xad,payload=body)
            targets=[n for n in sessions[0].dungeon_run.current['npcs']if xp_rules.eligible(n)]
            assert len(targets)>=2
            target=targets[0];base=xp_rules.identity(sessions[1],target)['base_experience']
            before_xp=read('SELECT uid,experience FROM reward_balances ORDER BY uid')
            with patch('els_server.domain.hot_time.ordinary_multiplier',return_value=1):
                await teacher.query(0xad,death(target).payload,reply=0xae)
                for peer in peers:await barrier(peer)
            after_xp=read('SELECT uid,experience FROM reward_balances ORDER BY uid')
            assert after_xp[0][1]==before_xp[0][1]
            assert after_xp[1][1]-before_xp[1][1]==base*2,(base,before_xp,after_xp)
            assert after_xp[2][1]-before_xp[2][1]==base,(base,before_xp,after_xp)
            receipts=read('SELECT identity_json,experience FROM pve_kill_experience WHERE owner=?',(uid[1],))
            assert json.loads(receipts[0][0])['mentor']['xp_percent']==100
            await teacher.query(0xad,death(target).payload,reply=0xae)
            assert read('SELECT uid,experience FROM reward_balances ORDER BY uid')==after_xp
            report['checks'].append('Actual authenticatedAD gives student2x and outsider1x from the same issued NPC; teacher receives0 at blocked99; frozen mentor source saved; repeated death cannot award again')
            target=targets[1]
            def dump():
                with closing(sqlite3.connect(cfg.state_file))as db:return list(db.iterdump())
            before=dump();old_defeated=[dict(s.defeated_npcs)for s in sessions]
            original_notice=dungeon_lifecycle.experience_death_notice
            def fail_student(index,killer,owner,amount):
                if owner==uid[1]:raise ValueError('Owned second memberXP encoder failure')
                return original_notice(index,killer,owner,amount)
            with patch.object(dungeon_lifecycle,'experience_death_notice',fail_student):
                rejected=await app.call(lambda:pve.group_death(app.world.dungeons,room,sessions[0],death(target)))
            assert rejected==[] and dump()==before and [s.defeated_npcs for s in sessions]==old_defeated
            report['checks'].append('Late studentXP encoding failure in the real shared death writer rolls back every SQL row and preserves all original NPC states')
'''
source=source[:begin]+cases+source[end:]
source=source.replace("index+1,'mentor-tls-'", "(1 if index==1 else index+1),'mentor-tls-'")
source=source.replace("ServerConfig(mode='friends',host=", "ServerConfig(mode='friends',friends_coop_enabled=True,host=")
source=source.replace("'relation-tls-'","'party-play-tls-'")
source=source.replace('    app=server=None;peers=[];events=[]',
    '    report["foundation_sha256"]=FOUNDATION_SHA\n    app=server=None;peers=[];events=[]')
source=source.replace("except BaseException:report['error']=traceback.format_exc()",
    "except BaseException:\n            report['error']=traceback.format_exc()\n            report['failure_events']=[{k:row[k]for k in('event','error','reason','detail')if k in row}for row in events[-20:]]")
prefix='\n'.join(original.splitlines()[:node.lineno-1]);FOUNDATION_SHA=hashlib.sha256(foundation.read_bytes()).hexdigest()
exec(compile(prefix,str(foundation),'exec'),globals())
generated=Path(__file__).with_name('generated-party-play-main.py');generated.write_text(source+'\n','utf8')
exec(compile(source,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
