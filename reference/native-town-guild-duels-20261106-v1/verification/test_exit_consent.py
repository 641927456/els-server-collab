"""Only the newly restored6A/6B/6C exit path, with explicit HP fixtures."""
from test_duel_tls import (W,C,Application,ServerConfig,GameServer,Characters,LocalState,
    catalog,create,connect,action,ws)
from contextlib import closing
from pathlib import Path
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback

async def main():
    report=dict(ok=False,private_authenticated_TLS=True,native_game=False,
        support_and_HP='explicit fixtures',checks=[],source_files={p.relative_to(C).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in C.rglob('*.py')})
    app=server=None;peers=[];events=[]
    with tempfile.TemporaryDirectory(prefix='owned-duel-exit-',dir=W)as name:
        own=Path(name);create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'own.sqlite3',accounts_file=own/'accounts.sqlite3',tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for letter,family in(('A',1),('B',10)):
                identity=app.registry.create('ownedexit'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('Exit'+letter,family,'exit-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(identity=identity,uid=uid,name='Exit'+letter))
            server=GameServer(cfg,app,lambda event,**kw:events.append(dict(event=event,**kw)));_,port=await server.start()
            for value in values:
                identity=value['identity'];value['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
                await connect(value,peers)
            sessions=[app.playing[v['identity']['id']]for v in values];pvp=app.world.pvp
            witness=object();await app.call(lambda:pvp.support.update({s.account.account_id:(witness,'own','own',True)for s in sessions}))
            async def observed(p,kind,start):return next((e for e in p.received[start:]if e.kind==kind),None)or await p.until(kind)
            def saved():
                with closing(sqlite3.connect(cfg.state_file))as db:
                    names=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name NOT LIKE 'native_duel_%'")]
                    return {n:sorted(db.execute('SELECT *FROM "'+n+'"'),key=repr)for n in names}
            baseline=saved()
            for attempt in range(2):
                starts=[len(p.received)for p in peers]
                await action(peers[0],0x5c6,struct.pack('>QIQI',values[0]['uid'],0,values[1]['uid'],0)+ws(values[0]['name'])+bytes(9))
                notice=await observed(peers[1],0x5c8,starts[1]);offset=28+struct.unpack_from('>I',notice.payload,24)[0]
                await peers[1].send(0x5c9,struct.pack('>QQi',values[0]['uid'],values[1]['uid'],0)+notice.payload[offset:-5]+bytes(8))
                for p,start in zip(peers,starts):await observed(p,0x34b,start)
                for p in peers:await action(p,0x91,struct.pack('>iI',100,0))
                room=pvp.room(sessions[0]);assert room.phase=='active'
                if attempt==1:
                    await action(peers[0],0xa7,struct.pack('>iQQBffi?',-1,values[1]['uid'],values[1]['uid'],0,0.,0.,-1,False))
                    starts=[len(p.received)for p in peers];await peers[0].send(0xaa)
                    for p,start in zip(peers,starts):await observed(p,0x9d,start)
                    for p,hp in zip(peers,(0.,23456.)):await action(p,0x9e,struct.pack('>f',hp)+bytes(178))
                    assert room.phase=='result'
                starts=[len(p.received)for p in peers]
                await action(peers[0],0x6a,reply=0x6b)
                departure=await observed(peers[0],0x6c,starts[0])
                assert struct.unpack_from('>bQI',departure.payload)==(5,values[0]['uid'],2)
                assert pvp.room(sessions[0])is None and sessions[0].phase=='map_loading'
                assert pvp.room(sessions[1])is room and room.phase=='result'
                if attempt==0:
                    for p,start in zip(peers,starts):await observed(p,0xc2,start)
                await action(peers[1],0x6a,reply=0x6b);await observed(peers[1],0x6c,starts[1])
                for p in peers:
                    await action(p,0x225,struct.pack('>iB',20001,0))
                    await action(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
                assert not pvp.loading.rooms and not pvp.duels.returning
                assert all(s.phase=='town_ready'and not s.dungeon_return_pending for s in sessions)
                assert saved()==baseline
                with closing(sqlite3.connect(cfg.state_file))as db:assert db.execute('SELECT COUNT(*)FROM native_duel_results').fetchone()==(attempt+1,)
                report['checks'].append(('active departure'if attempt==0 else'already completed result')+'6A/6B/6C and both actual225/227 returns; one ledger, all other SQL rows unchanged')
            report['ok']=True
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in reversed(peers):await p.close()
            if server is not None:await server.close()
            if app is not None:app.close()
    report['worker_errors']=[e for e in events if e['event']in('worker_error','notification_error','connection_task_error')]
    report['ok']=report['ok']and not report['worker_errors'];report['owned_directory_removed']=not own.exists()
    out=W/('exit-consent-'+str(time.time_ns())+'.json');out.write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],error=report.get('error'),worker_errors=report['worker_errors'],evidence=str(out))))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
