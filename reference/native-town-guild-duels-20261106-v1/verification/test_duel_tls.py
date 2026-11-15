"""Native request lifecycle on owned TLS actors; HP/support are explicit fixtures."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;R=Path('G:/els')
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca';C=W/'candidate/els_server'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(B/'tools/pylibs'),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(W.parent/'delivery-guild-v1')]
_sqlite=ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import els_server,els_server.domain,els_server.storage,els_server.protocol
for namespace,sub in((els_server.domain,'domain'),(els_server.protocol,'protocol'),(els_server.storage,'storage')):
    namespace.__path__.insert(0,str(C/sub))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.town_travel import catalog
from els_server.protocol.local_messages import wstring as ws
from tools.create_friends_certificate import create
from native_peer import connect
from combined_qa_client import action,enter,leave

async def main():
    report=dict(ok=False,private_authenticated_TLS=True,native_game=False,natural_GUI=False,
        native_HP_and_support='explicit business fixtures; actual signed-client qualification pending',
        production_database_access=False,checks=[],source_files={p.relative_to(C).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in C.rglob('*.py')})
    app=server=None;peers=[];events=[]
    with tempfile.TemporaryDirectory(prefix='owned-duel-tls-',dir=W)as name:
        own=Path(name);create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'own.sqlite3',accounts_file=own/'accounts.sqlite3',
            tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for index,letter in enumerate('ABC'):
                identity=app.registry.create('owneddueltls'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('DuelTLS'+letter,(1,10,15)[index],'duel-tls-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(identity=identity,uid=uid,character_name='DuelTLS'+letter))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99 WHERE uid=?',(values[0]['uid'],))
                db.execute('UPDATE reward_balances SET ed=6000000 WHERE uid=?',(values[0]['uid'],))
            server=GameServer(cfg,app,lambda event,**kw:events.append(dict(event=event,**kw)));_,port=await server.start()
            for value in values:
                identity=value['identity'];value['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],
                    certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
                await connect(value,peers)
            master,guest,other=peers;uid=[v['uid']for v in values]
            sessions=[app.playing[v['identity']['id']]for v in values];pvp=app.world.pvp
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            def assets():
                with closing(sqlite3.connect(cfg.state_file))as db:
                    tables=['characters','character_owners','inventory_items','reward_balances','location','character_quests']
                    tables += [n for n, in db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'official_pvp_%'AND type='table'")]
                    return {table:sorted(db.execute('SELECT * FROM "'+table+'"'),key=repr)for table in tables}
            def received(p,kind,start):return next((e for e in p.received[start:]if e.kind==kind),None)
            async def event_after(p,kind,start):return received(p,kind,start)or await p.until(kind)
            async def invite(first,second,expected=0):
                body=struct.pack('>QIQI',uid[first],0,uid[second],0)+ws(values[first]['character_name'])+struct.pack('>IBi',0,0,0)
                start=len(peers[second].received)
                ack=await peers[first].query(0x5c6,body)
                assert struct.unpack('>iQ',ack.payload)==(expected,uid[second]),ack.payload.hex()
                if expected:return None
                incoming=await event_after(peers[second],0x5c8,start)
                offset=28+struct.unpack_from('>I',incoming.payload,24)[0]
                assert incoming.payload[-5:]==bytes(5)
                return incoming.payload[offset:-5]
            async def answer(first,second,body,decision):
                await peers[second].send(0x5c9,struct.pack('>QQi',uid[first],uid[second],decision)+body+bytes(8))
            # Refusal persists the exact source rule across subsequent requests.
            full=await invite(0,1);start=len(master.received);await answer(0,1,full,1)
            assert struct.unpack('>iQ',(await event_after(master,0x5ca,start)).payload)==(1679,uid[1])
            saved=read('SELECT inviter,recipient,generation,until FROM native_duel_refusals')
            assert len(saved)==1 and 595<=saved[0][3]-int(time.time())<=600
            await invite(0,1,1680)
            start=len(master.received);full=await invite(0,2);await answer(0,2,full,2)
            assert struct.unpack('>iQ',(await event_after(master,0x5ca,start)).payload)==(1678,uid[2])
            assert read('SELECT inviter,recipient,generation,until FROM native_duel_refusals')==saved
            report['checks'].append('manual refusal persists600s pair cooldown; automatic busy refusal creates no economic/cooldown write')
            # A missing native support witness refuses without stranding consent.
            full=await invite(0,2);starts=[len(master.received),len(other.received)]
            await answer(0,2,full,0)
            for p,start in zip((master,other),starts):assert struct.unpack_from('>i',(await event_after(p,0x5ca,start)).payload)[0]==1678
            assert not pvp.duels.pending and all(s.phase=='town_ready'for s in sessions)
            report['checks'].append('missing native HP support refuses and frees both invitations; both connections remain usable')
            # This fixture enables only the pre-existing trusted readiness map.
            witness=object()
            await app.call(lambda:pvp.support.update({s.account.account_id:(witness,'owned-fixture','owned-fixture',True)for s in(sessions[0],sessions[2])}))
            async def battle(guild=False):
                before=assets();full=await invite(0,2);starts=[len(master.received),len(other.received)]
                await answer(0,2,full,0)
                admissions=[await event_after(p,0x34b,start)for p,start in zip((master,other),starts)]
                room=pvp.room(sessions[0]);assert room is pvp.room(sessions[2])and room.kind=='challenge'
                assert sessions[1]in app.world.members and all(s not in app.world.members for s in(sessions[0],sessions[2]))
                assert all(a.payload==admissions[0].payload for a in admissions)
                # Late pre-battle cancellation cannot terminate an admitted room.
                await master.send(0x5cb,b'\1');await master.query(0x48d,reply=0x48f)
                assert pvp.room(sessions[0])is room
                if guild:
                    for p in(master,other):await p.send(0x828,struct.pack('>fff',0.,0.,0.))
                starts=[len(master.received),len(other.received)]
                for p in(master,other):await action(p,0x91,struct.pack('>iI',100,0))
                for p,start in zip((master,other),starts):await event_after(p,0x96,start)
                assert room.phase=='active'
                await action(master,0xa7,struct.pack('>iQQBffi?',-1,uid[2],uid[2],0,0.,0.,-1,False))
                starts=[len(master.received),len(other.received)];await master.send(0xaa)
                for p,start in zip((master,other),starts):await event_after(p,0x9d,start)
                starts=[len(master.received),len(other.received)]
                await action(master,0x9e,struct.pack('>f',0.)+bytes(178))
                await action(other,0x9e,struct.pack('>f',23456.)+bytes(178))
                for p,start in zip((master,other),starts):
                    result=await event_after(p,0xc2,start)
                    for i in(0,1):
                        row=struct.unpack_from('>Q8iB',result.payload,23+i*448)
                        assert row[5:7]==(0,0)and row[8]==0,row
                assert room.phase=='result'and assets()==before
                count=read('SELECT COUNT(*) FROM native_duel_results')[0][0]
                await action(other,0x9e,struct.pack('>f',23456.)+bytes(178))
                assert read('SELECT COUNT(*) FROM native_duel_results')[0][0]==count
                if guild:
                    # Real result-screen direct4FB and native67->68->4FB paths.
                    await action(other,0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000))
                    await action(other,0x504,struct.pack('>fffBH',0.,0.,0.,0,0))
                    await action(master,0x67,bytes(4)+struct.pack('>f',0.)+bytes(178)+bytes(4),reply=0x68)
                    await enter(master)
                    assert all(s.phase=='guild_agit_ready'for s in(sessions[0],sessions[2]))
                    assert all(s.guild_agit is not None and not s.dungeon_return_pending for s in(sessions[0],sessions[2]))
                else:
                    for p in(master,other):
                        await action(p,0x225,struct.pack('>iB',20001,0))
                        await action(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
                    assert all(s.phase=='town_ready'for s in sessions)
                assert not pvp.duels.returning and not pvp.duels.positions
                assert all(pvp.room(s)is None for s in(sessions[0],sessions[2]))
                assert assets()==before
                report['checks'].append(('GuildAgit'if guild else'Town')+' invite/accept/34B/91/96/A7/AA/9E/C2/return closes with zero reward/ranking/quest/asset changes; replay adds no result')
            await battle()
            report['checks'].append('99/1 actors enter the same challenge; no official queue level gate or profile creation')
            await action(master,0xea,struct.pack('>BHIiii',0,0,1,110845,1,10018))
            ticket=read('SELECT uid FROM inventory_items WHERE owner=?AND template=110845',(uid[0],))[0][0]
            await action(master,0x276,struct.pack('>Q',ticket)+ws('DuelG'+str(uid[0]))+ws(''))
            guild=read('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid[0],))[0][0]
            await action(master,0x285,ws(values[2]['character_name'])+struct.pack('>Q',uid[2]));await other.until(0x287)
            await action(other,0x288,struct.pack('>i',guild)+ws(values[0]['character_name'])+bytes(4))
            await enter(master);await enter(other)
            await invite(1,0,1678)
            await battle(True)
            await leave(master);await leave(other)
            report['ok']=True
        except BaseException:report.update(ok=False,error=traceback.format_exc())
        finally:
            for p in reversed(peers):
                try:await p.close()
                except BaseException:report.update(ok=False,cleanup_error=traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['worker_errors']=[e for e in events if e['event']in('worker_error','notification_error','connection_task_error')]
    if report['worker_errors']:report['ok']=False
    report['owned_directory_removed']=not own.exists()
    out=W/('duel-tls-'+str(time.time_ns())+'.json');out.write_bytes((json.dumps(report,indent=2)+'\n').encode('utf8'))
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],evidence=str(out),error=report.get('error'),cleanup_error=report.get('cleanup_error'),worker_errors=report['worker_errors'])))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
