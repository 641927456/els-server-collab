"""Six real authenticated actors, selected owned mounts and original admission.

Owned mount inventory and direct admission are explicit setup fixtures. This
qualifies routing/loading exit, not acquisition, matching, racing or rewards.
"""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
original=W.parent/'independent-delivery-v4/verify_photo_tls.py'
source=original.read_text('utf8');tree=ast.parse(source)
main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
prefix='\n'.join(source.splitlines()[:main.lineno-1]);body=ast.get_source_segment(source,main)
count="count=3 if '--social-only'in __import__('sys').argv else 2 if any(a in __import__('sys').argv for a in('--entry-only','--unlock-only'))else 9"
assert count in body;body=body.replace(count,'count=6')
needle="            stage='nine native logins'"
setup='''            from els_server.storage import companion_state
            from els_server.domain.companions import catalog as companion_catalog
            template,definition=next((key,value)for key,value in sorted(companion_catalog()['mount'].items())
                if value['duration']==-1 and len(value['outcomes'])==1 and value['outcomes'][0][0]<10000)
            unit=definition['outcomes'][0][0];mounts=[9000001+i for i in range(count)]
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                companion_state.ensure(db)
                for index,owner in enumerate(uids):
                    db.execute('INSERT INTO companions VALUES(?,?,?,?,?,?)',(mounts[index],owner,'mount',unit,'OwnedRouteMount',template))
            report.update(mount_inventory_is_explicit_owned_fixture=True,matching_qualified=False,race_outcome_qualified=False)
'''
assert needle in body;body=body.replace(needle,setup+"            stage='six native logins'")
start=body.index("            if '--social-only'");end=body.index("            report['passed']=True",start)
cases='''            from unittest.mock import patch
            stage='original mount selection and admission'
            for index in range(count):
                await action(index,0xa89,struct.pack('>Q',mounts[index]),0xa8a)
                await action(index,0xa8b,struct.pack('>QB',mounts[index],1),0xa8c)
            members=tuple(live(i)for i in range(count));racing=app.world.racing
            await app.call(racing.admit,members,members[0])
            for peer in peers:await peer.until(0x14a)
            room=racing.room(live(0));assert room.phase=='loading'and len(room.members)==6
            def snapshot_check():
                called=[];actual=racing.current
                def current(s,r):called.append(s);return actual(s,r)
                with patch.object(racing,'current',side_effect=current):app.realtime.publish(app,lambda:None,())
                expected={(p.account.account_id,room.seed,other.account.uid):(other.account.account_id,p.account.uid)
                    for p in members for other in members if other is not p}
                assert len(called)==6 and set(called)==set(members)
                assert dict(app.realtime.view.routes)==expected and len(expected)==30
                for p in members:
                    value=json.loads(app.realtime.view.manifests[p.account.account_id][1:])
                    assert value['peers']==[dict(uid=m.account.uid,port=21100+i)for i,m in enumerate(members)]
                victim=live(4);token=victim.shop_session_id
                try:
                    victim.shop_session_id=str(__import__('uuid').uuid4())
                    app.realtime.publish(app,lambda:None,());assert not app.realtime.view.routes
                finally:victim.shop_session_id=token
                app.realtime.publish(app,lambda:None,());assert dict(app.realtime.view.routes)==expected
            await app.call(snapshot_check)
            report['checks'].append('Six actual selected mounts and production room admission deliver original14A; one publication executes6 unchanged current-actor predicates exactly once and derives30 routes; changed session generation revokes the room and valid state is rechecked on the next publication')
            stage='six authenticated production relays'
            for index in range(count):relays.append(await peers[index].bridge.remote(role='relay'))
            async def packet(reader,kind):
                async with asyncio.timeout(8):
                    while True:
                        value=await read_packet(reader)
                        if value[0]==kind:return value
            values=await asyncio.gather(*(packet(reader,1)for reader,writer in relays))
            manifests=[json.loads(value[1:])for value in values]
            assert all(v['epoch']==room.seed and len(v['peers'])==6 for v in manifests)
            for index in range(1,6):
                raw=data_packet(room.seed,uids[index],b'owned-six-racing-route')
                relays[0][1].write(struct.pack('>I',len(raw))+raw)
            await relays[0][1].drain()
            received=await asyncio.gather(*(packet(reader,2)for reader,writer in relays[1:]))
            assert all(read_data(value)==(room.seed,uids[0],b'owned-six-racing-route')for value in received)
            report['checks'].append('Six authenticated production TLS relay sockets expose the same current6-slot manifest; actual sender bytes reach all5 permitted peers with authoritative sender UID')
            stage='native loading leave retains original peer ports'
            old=env.HERE/'native-racing-return-1793935212983217700.json'
            layout=json.loads(old.read_text('utf8'));assert layout['ok']and layout['original_writers_unmodified']
            leave=bytes.fromhex(layout['wire_hex'])
            assert leave[:4]==struct.pack('>i',0x72) and 100<=len(leave)<=8192
            await peers[0].send(0x67,leave);assert(await peers[0].until(0x68)).payload[:4]==bytes(4)
            assert racing.room(live(0))is None and all(racing.room(live(i))is room for i in range(1,6))
            value=await app.call(app.world.dungeons.manifest,app,identities[1]['id'])
            assert value['peers']==[dict(uid=u,port=21100+i)for i,u in enumerate(uids)]
            assert await app.call(app.world.dungeons.relay_target,app,identities[1]['id'],room.seed,uids[0])is None
            assert await app.call(app.world.dungeons.relay_target,app,identities[1]['id'],room.seed,uids[5])==(identities[5]['id'],uids[1])
            assert len(app.realtime.view.routes)==20
            for kind,reply,raw in((0x225,0x226,struct.pack('>iB',20001,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
                await action(0,kind,raw,reply)
            assert assets()==before
            report['checks'].append('Current racing reason0x72 with original native statistic writer: controlled67/68 loading departure returns the actual actor to town, removes every route to/from that actor and preserves all6 original port assignments for5 remaining peers;20 surviving routes remain, with no inventory, ED, saved location or ownership change; not natural Game exit')
            errors=[row for row in logs if row['event']in('worker_error','notification_error','connection_task_error')]
            assert not errors,errors
'''
begin=cases.index('            def snapshot_check():')
segment_end=cases.index("            stage='native loading leave retains original peer ports'")
reuse='''            if '--leave-only'in __import__('sys').argv:
                proof=env.HERE/'racing-routing-TLS-1793934964552716800.json'
                earlier=json.loads(proof.read_text('utf8'))
                assert earlier['passed']is False and earlier['stage']=='native loading leave retains original peer ports'
                previous={Path(k).as_posix():v for k,v in earlier['loaded_candidate'].items()}
                assert all(previous[p.relative_to(env.HERE/'candidate').as_posix()]==hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in(env.HERE/'candidate').rglob('*.py'))
                assert len(earlier['checks'])==3
                report['checks']+=earlier['checks'][1:]
                report['reused_successful_scope']=dict(source=proof.name,sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),
                    cases='Six-member current-authority publication and actual6-socket TLS fanout only; original wrong-reason exit fixture remains a failed result')
            else:
'''
cases=cases[:begin]+reuse+'\n'.join('    '+line if line else line for line in cases[begin:segment_end].splitlines())+'\n'+cases[segment_end:]
body=body[:start]+cases+body[end:]
body=body.replace("'owned-photo-tls-'","'owned-racing-routing-tls-'").replace("'private-TLS-'","'racing-routing-TLS-'")
ast.parse(body);generated=W/'generated-racing-routing-TLS.py';generated.write_text(body+'\n','utf8')
exec(compile(prefix,str(original),'exec'),globals());exec(compile(body,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(0 if asyncio.run(main())else 1)
