"""Real Application actors and native rounds; controlled room fixture only.

This qualifies the new ledger, not invitation admission, a played match or UI.
"""
from pathlib import Path
from dataclasses import replace
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;R=Path('G:/els')
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
C=W/'candidate/els_server'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(B/'tools/pylibs'),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(W.parent/'delivery-guild-v1')]
import ctypes
_sqlite=ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import els_server,els_server.domain,els_server.storage,els_server.protocol
els_server.storage.__path__.insert(0,str(C/'storage'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.town_travel import catalog
from els_server.domain.pvp_loading import Room
from els_server.domain.pvp_registration import Ticket,_binding
from els_server.storage import duel_results
from els_server.protocol.protocol_codec import Event
from tools.create_friends_certificate import create
from native_peer import connect

async def main():
    report=dict(ok=False,source_release='native-guild-complete-20261105-v2',
        candidate_sha256=hashlib.sha256((C/'storage/duel_results.py').read_bytes()).hexdigest(),
        private_authenticated_TLS_actors=True,explicit_round_fixture=True,
        invitation_admission_qualified=False,native_game=False,production_database_access=False,checks=[])
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-duel-ledger-',dir=W)as name:
        own=Path(name);create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=own/'own.sqlite3',
            accounts_file=own/'accounts.sqlite3',tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();identities=[]
            for letter in'AB':
                identity=app.registry.create('ownedduel'+letter.lower())
                uid=Characters(cfg.state_file,identity['id']).create('DuelSQL'+letter,1,'own-duel-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                identities.append(dict(identity=identity,uid=uid))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw)))
            _,port=await server.start()
            for value in identities:
                identity=value['identity']
                value['bridge']=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],
                    certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
                await connect(value,peers)
            def exercise():
                one,two=(app.playing[v['identity']['id']]for v in identities)
                pvp=app.world.pvp;members=(one,two)
                tickets=tuple(Ticket(s,'duel-sql-'+str(i),_binding(s),'duel-sql',None,time.monotonic())for i,s in enumerate(members))
                # Explicit active-room fixture; no forged native start/death.
                for s in members:
                    app.world.leave(s);s.phase='pvp_active';s.active_map=s.pending_map=1
                room=Room(880001,'own-duel-ledger-seed',members,tickets,1,(),(),
                    phase='active',loaded=frozenset(members),started=time.monotonic()-12)
                room.kind='challenge'
                for s in members:pvp.loading.rooms[s]=room
                E=lambda k,p=b'':Event(0x202,kind=k,payload=p)
                pvp.rounds.death(one,E(0xa7,struct.pack('>iQQBffi?',-1,two.account.uid,two.account.uid,0,0,0,-1,False)),11)
                pvp.rounds.complete(one,E(0xaa))
                pvp.rounds.report(one,E(0x9e,struct.pack('>f',0)+bytes(178)),13)
                pvp.rounds.report(two,E(0x9e,struct.pack('>f',23456)+bytes(178)),14)
                def snapshot():
                    with closing(sqlite3.connect(cfg.state_file))as db:
                        tables=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name!='native_duel_results'ORDER BY name")]
                        return {n:tuple(sorted(db.execute('SELECT * FROM "'+n.replace('"','""')+'"'),key=repr))for n in tables}
                def exists():
                    with closing(sqlite3.connect(cfg.state_file))as db:return db.execute("SELECT 1 FROM sqlite_master WHERE name='native_duel_results'").fetchone()is not None
                before=snapshot()
                def broken(db,sealed,rows):raise ValueError('owned encoder failure')
                try:duel_results.settle(pvp.rounds,one,encode=broken)
                except ValueError as e:assert str(e)=='owned encoder failure'
                else:raise AssertionError('encoder failure accepted')
                assert snapshot()==before and not exists()
                report['checks'].append('encoder failure rolls back; no ledger or asset changes')
                def diagnostic(db,sealed,rows):
                    assert db.in_transaction and sealed.killer is two
                    assert all(row['rating_delta']==row['ap_delta']==row['awarded_exp']==0 for row in rows)
                    # Labelled diagnostic payload; actual C2 encoder tested separately.
                    return {s:(Event(0x201,kind=0xc2,payload=b'OWNED-SQL-ONLY'),)for s in members}
                events,receipt,replayed=duel_results.settle(pvp.rounds,one,encode=diagnostic)
                assert not replayed and snapshot()==before
                assert [row['win']for row in receipt['rows']]==[False,True]
                report['checks'].append('real sealed result stored once; all pre-existing SQL tables byte-value unchanged')
                with closing(sqlite3.connect(cfg.state_file))as db:
                    assert db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'official_pvp_%'").fetchall()==[]
                    saved=db.execute('SELECT result_json FROM native_duel_results WHERE seed=?',(room.seed,)).fetchone()[0]
                    assert json.loads(saved)==receipt
                report['checks'].append('cold result read exact; no official profile or registration required/created')
                def no_encoder(*args):raise AssertionError('replay invoked encoder')
                assert duel_results.settle(pvp.rounds,two,encode=no_encoder)==(events,receipt,True)
                assert snapshot()==before
                report['checks'].append('other actor replay returns persisted events without another write or reward')
                round_=pvp.rounds.rounds[room.seed];sealed=round_.sealed
                round_.sealed=replace(sealed,elapsed=sealed.elapsed+1)
                try:duel_results.settle(pvp.rounds,one,encode=no_encoder)
                except ValueError as e:assert str(e)=='Duel conflicting result receipt'
                else:raise AssertionError('conflicting proof accepted')
                round_.sealed=sealed
                assert snapshot()==before
                report['checks'].append('changed sealed proof cannot reuse result seed')
                for s in members:pvp.loading.rooms.pop(s);s.phase='map_loading'
                pvp.rounds.rounds.pop(room.seed)
            await app.call(exercise)
            report['ok']=True
        except BaseException:report.update(ok=False,error=traceback.format_exc())
        finally:
            # A failed ledger assertion must still retire this explicit fixture
            # before the ordinary disconnect path owns the real TLS actors.
            if app is not None:
                def retire_fixture():
                    pvp=app.world.pvp
                    for s,room in tuple(pvp.loading.rooms.items()):
                        if room.seed=='own-duel-ledger-seed':
                            pvp.loading.rooms.pop(s);s.phase='map_loading'
                    pvp.rounds.rounds.pop('own-duel-ledger-seed',None)
                await app.call(retire_fixture)
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.update(ok=False,cleanup_error=traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['worker_errors']=[e for e in errors if e['event']in('worker_error','notification_error','connection_task_error')]
    if report['worker_errors']:report['ok']=False
    report['owned_directory_removed']=not own.exists()
    p=W/('result-sql-'+str(time.time_ns())+'.json');p.write_bytes((json.dumps(report,indent=2)+'\n').encode('utf8'))
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],evidence=str(p),error=report.get('error'),cleanup_error=report.get('cleanup_error'))))
    return report['ok']
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
