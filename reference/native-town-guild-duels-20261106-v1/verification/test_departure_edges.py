"""Guild departure during a live duel and actual completed Town return."""
from test_duel_tls import (W,C,Application,ServerConfig,GameServer,Characters,LocalState,
    catalog,create,connect,action,enter,leave,ws)
from contextlib import closing
from pathlib import Path
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback

async def main():
    report=dict(ok=False,private_authenticated_TLS=True,native_game=False,production_database_access=False,
        support_and_HP='explicit business fixtures',checks=[],source_files={p.relative_to(C).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in C.rglob('*.py')})
    app=server=None;peers=[];events=[]
    with tempfile.TemporaryDirectory(prefix='owned-duel-departure-',dir=W)as name:
        own=Path(name);create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'own.sqlite3',accounts_file=own/'accounts.sqlite3',
            tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for letter in'ABC':
                identity=app.registry.create('owndueledge'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('DuelEdge'+letter,1,'own-edge-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(identity=identity,uid=uid,name='DuelEdge'+letter))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99 WHERE uid=?',(values[2]['uid'],))
                db.execute('UPDATE reward_balances SET ed=6000000 WHERE uid=?',(values[2]['uid'],))
            server=GameServer(cfg,app,lambda event,**kw:events.append(dict(event=event,**kw)));_,port=await server.start()
            for value in values:
                identity=value['identity'];value['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],
                    certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
                await connect(value,peers)
            first,second,master=peers;uid=[v['uid']for v in values]
            sessions=[app.playing[v['identity']['id']]for v in values];pvp=app.world.pvp
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            async def observed(p,kind,start):return next((e for e in p.received[start:]if e.kind==kind),None)or await p.until(kind)
            async def invite(a,b):
                start=len(peers[b].received)
                ack=await peers[a].query(0x5c6,struct.pack('>QIQI',uid[a],0,uid[b],0)+ws(values[a]['name'])+bytes(9))
                assert ack.payload[:4]==bytes(4),ack.payload.hex()
                notice=await observed(peers[b],0x5c8,start);offset=28+struct.unpack_from('>I',notice.payload,24)[0]
                return notice.payload[offset:-5]
            full=await invite(1,2);start=len(second.received)
            await master.send(0x5c9,struct.pack('>QQi',uid[1],uid[2],1)+full+bytes(8));await observed(second,0x5ca,start)
            definition=read("SELECT sql FROM sqlite_master WHERE name='native_duel_refusals'")[0][0]
            with closing(sqlite3.connect(':memory:'))as db:
                db.execute('PRAGMA foreign_keys=ON');db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY)')
                db.execute(definition);db.executemany('INSERT INTO characters VALUES(?)',[(1,),(2,),(3,)])
                db.executemany('INSERT INTO native_duel_refusals VALUES(?,?,?,?)',[(1,2,'one',600),(3,1,'two',600)])
                db.execute('DELETE FROM characters WHERE uid=1')
                assert db.execute('SELECT *FROM native_duel_refusals').fetchall()==[]
            report['checks'].append('actual writer-created refusal schema cascades both deleted-inviter and deleted-recipient rows in real SQLite')
            await action(master,0xea,struct.pack('>BHIiii',0,0,1,110845,1,10018))
            ticket=read('SELECT uid FROM inventory_items WHERE owner=?AND template=110845',(uid[2],))[0][0]
            await action(master,0x276,struct.pack('>Q',ticket)+ws('DuelE'+str(uid[2]))+ws(''))
            guild=read('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid[2],))[0][0]
            for i,p in enumerate((first,second)):
                await action(master,0x285,ws(values[i]['name'])+struct.pack('>Q',uid[i]));await p.until(0x287)
                await action(p,0x288,struct.pack('>i',guild)+ws(values[2]['name'])+bytes(4))
            for p in peers:await enter(p)
            witness=object();await app.call(lambda:pvp.support.update({s.account.account_id:(witness,'owned-fixture','owned-fixture',True)for s in sessions[:2]}))
            full=await invite(0,1);starts=[len(p.received)for p in(first,second)]
            await second.send(0x5c9,struct.pack('>QQi',uid[0],uid[1],0)+full+bytes(8))
            for p,start in zip((first,second),starts):await observed(p,0x34b,start)
            for p in(first,second):await action(p,0x91,struct.pack('>iI',100,0))
            room=pvp.room(sessions[0]);assert room.phase=='active'
            await action(master,0x290,struct.pack('>QB',uid[1],1))
            assert read('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid[1],))==[]
            assert pvp.room(sessions[1])is room and sessions[1].coop_error is None
            await action(first,0xa7,struct.pack('>iQQBffi?',-1,uid[1],uid[1],0,0.,0.,-1,False))
            starts=[len(p.received)for p in(first,second)];await first.send(0xaa)
            for p,start in zip((first,second),starts):await observed(p,0x9d,start)
            for p,hp in((first,0.),(second,23456.)):await action(p,0x9e,struct.pack('>f',hp)+bytes(178))
            assert room.phase=='result'
            # Removed Guild member: normal67/68, denied4FB, original Town
            # fallback225/227. The completed return authority must then retire.
            await action(second,0x67,bytes(4)+struct.pack('>f',23456.)+bytes(178)+bytes(4),reply=0x68)
            await action(second,0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),success=False)
            for p in(second,first):
                await action(p,0x225,struct.pack('>iB',20001,0))
                await action(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
            assert all(s.phase=='town_ready'and not s.dungeon_return_pending for s in sessions[:2])
            # Existing member chose Town instead of original GuildAgit; its
            # next actual admission must not inherit a stale duel return.
            await enter(first);await action(first,0x508)
            await action(second,0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),success=False)
            assert not pvp.duels.returning and not pvp.loading.rooms and not pvp.duels.positions
            assert all(s.coop_error is None for s in sessions)
            report['checks'].append('Guild kick during active duel retains real battle; removed member returns through67/68/denied4FB/225/227; existing member can choose Town and re-enter GuildAgit')
            await leave(first);await leave(master)
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
    out=W/('departure-edges-'+str(time.time_ns())+'.json');out.write_bytes((json.dumps(report,indent=2)+'\n').encode('utf8'))
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],evidence=str(out),error=report.get('error'),cleanup_error=report.get('cleanup_error'),worker_errors=report['worker_errors'])))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
