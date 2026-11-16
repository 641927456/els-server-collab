"""Changed shared loading/result flow retains ordinary official1v1 behavior."""
from test_duel_tls import (W,C,Application,ServerConfig,GameServer,Characters,LocalState,
    catalog,create,connect,action,ws)
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback

async def main():
    report=dict(ok=False,private_authenticated_TLS=True,production_database_access=False,native_game=False,
        support_and_HP='explicit business fixtures',checks=[],source_files={p.relative_to(C).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in C.rglob('*.py')})
    app=server=None;peers=[];events=[]
    with tempfile.TemporaryDirectory(prefix='owned-official-regression-',dir=W)as name:
        own=__import__('pathlib').Path(name);create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'own.sqlite3',accounts_file=own/'accounts.sqlite3',
            tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for letter in'AB':
                identity=app.registry.create('ownofficial'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('Official'+letter,1,'own-official-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(identity=identity,uid=uid,character_name='Official'+letter))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99')
                # Compatibility fixture: an already installed challenge ledger
                # must not be mistaken for unapproved historic official PvP.
                db.execute('CREATE TABLE native_duel_results(seed TEXT PRIMARY KEY,proof_hash TEXT NOT NULL,result_json TEXT NOT NULL)')
            server=GameServer(cfg,app,lambda event,**kw:events.append(dict(event=event,**kw)));_,port=await server.start()
            for value in values:
                identity=value['identity'];value['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],
                    certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
                await connect(value,peers)
            sessions=[app.playing[v['identity']['id']]for v in values];pvp=app.world.pvp;witness=object()
            await app.call(lambda:pvp.support.update({s.account.account_id:(witness,'owned-fixture','owned-fixture',True)for s in sessions}))
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            async def observed(p,kind,start):return next((e for e in p.received[start:]if e.kind==kind),None)or await p.until(kind)
            starts=[len(p.received)for p in peers]
            for p in peers:
                await action(p,0x7d4,struct.pack('>ii',5,0))
                await action(p,0x342,struct.pack('>IBBBiI',1,0,1,0,0,0))
            for p,start in zip(peers,starts):await observed(p,0x349,start)
            assert len(pvp.registrations.offers)==2
            starts=[len(p.received)for p in peers]
            for p in peers:await p.send(0x34a,b'\1\1\0'+bytes(4)+b'\0')
            for p,start in zip(peers,starts):await observed(p,0x34b,start)
            room=pvp.room(sessions[0]);assert room is pvp.room(sessions[1])and room.kind=='official'and room.origins==()
            report['checks'].append('ordinary7D4/342/349/two34A/34B still admits exactly the real official pair beside existing duel ledger')
            starts=[len(p.received)for p in peers]
            for p in peers:await action(p,0x91,struct.pack('>iI',100,0))
            for p,start in zip(peers,starts):await observed(p,0x96,start)
            await action(peers[0],0xa7,struct.pack('>iQQBffi?',-1,values[1]['uid'],values[1]['uid'],0,0.,0.,-1,False))
            starts=[len(p.received)for p in peers];await peers[0].send(0xaa)
            for p,start in zip(peers,starts):await observed(p,0x9d,start)
            starts=[len(p.received)for p in peers]
            for p,hp in zip(peers,(0.,23456.)):await action(p,0x9e,struct.pack('>f',hp)+bytes(178))
            for p,start in zip(peers,starts):await observed(p,0xc2,start)
            profiles=[json.loads(row[0])for row in read('SELECT profile_json FROM official_pvp_profiles ORDER BY uid')]
            assert [p['ap']for p in profiles]==[10,40],profiles
            assert [p['completed']for p in profiles]==[1,1]
            assert read('SELECT COUNT(*)FROM official_pvp_results')==[(1,)]
            assert read('SELECT COUNT(*)FROM native_duel_results')==[(0,)]
            assert all(row[0]>0 for row in read('SELECT experience FROM reward_balances ORDER BY uid'))
            report['checks'].append('official sealed result retains approved AP10/40 and positive XP; only official ledger changes')
            for p in peers:
                await action(p,0x225,struct.pack('>iB',20001,0))
                await action(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
            assert not pvp.loading.rooms and not pvp.rounds.rounds
            # Persist a manual challenge refusal, then retire the actual actor
            # connection and prove the fresh login reads that SQL cooldown.
            uid=[v['uid']for v in values]
            body=struct.pack('>QIQI',uid[0],0,uid[1],0)+ws(values[0]['character_name'])+bytes(9)
            start=len(peers[1].received);ack=await peers[0].query(0x5c6,body);assert ack.payload[:4]==bytes(4)
            invitation=await observed(peers[1],0x5c8,start);offset=28+struct.unpack_from('>I',invitation.payload,24)[0]
            full=invitation.payload[offset:-5];start=len(peers[0].received)
            await peers[1].send(0x5c9,struct.pack('>QQi',*uid,1)+full+bytes(8))
            assert struct.unpack_from('>i',(await observed(peers[0],0x5ca,start)).payload)[0]==1679
            saved=read('SELECT *FROM native_duel_refusals')
            await peers[0].close()
            async with asyncio.timeout(10):
                while values[0]['identity']['id']in app.playing:await asyncio.sleep(.05)
            await connect(values[0],peers);peers[0]=peers.pop()
            ack=await peers[0].query(0x5c6,body)
            assert struct.unpack('>iQ',ack.payload)==(1680,uid[1])
            assert read('SELECT *FROM native_duel_refusals')==saved
            report['checks'].append('actual disconnect and fresh authenticated login retain the same600s refusal without extending it')
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
    out=W/('official-regression-'+str(time.time_ns())+'.json');out.write_bytes((json.dumps(report,indent=2)+'\n').encode('utf8'))
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],evidence=str(out),error=report.get('error'),cleanup_error=report.get('cleanup_error'),worker_errors=report['worker_errors'])))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
