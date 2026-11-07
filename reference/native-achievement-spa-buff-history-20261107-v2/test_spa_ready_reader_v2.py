"""Cold1500 getter commits, ready rollback/replay and unchanged entry refusals."""
import sys
if '--baseline'in sys.argv:
    from qa_environment import F,R,B
    S=F/'source-v1'
else:
    from qa_environment_v2 import F,R,B
    S=F/'source-v2'
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback
sys.path.insert(0,str(F/'delivery-qa-v2'))
from achievement_protocol_client import connect
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain import fishing_village1500 as spa
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data
from create_friends_certificate import create


async def run():
    baseline='--baseline'in sys.argv;report=dict(ok=False,baseline_reproducer=baseline,checks=[],production_database_access=False,native_Game=False,natural_GUI=False)
    app=server=None;peers=[];errors=[];writes=[];probe_errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-spa-ready-',dir=F)as folder:
        own=Path(folder);create(own,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=4,state_file=own/'game.sqlite3',accounts_file=own/'accounts.sqlite3',tls_cert=own/'server-cert.pem',tls_key=own/'server-key.pem',log_dir=own/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for index,(town,level)in enumerate(((1500,99),(20000,9),(20000,99))):
                auth=app.registry.create('ownedspaready'+str(index));name='SpaReady'+str(index)
                uid=Characters(cfg.state_file,auth['id']).create(name,index+1,'owned-ready:'+str(index))['uid']
                LocalState(cfg.state_file,uid).save(town,0,0,(0.,0.,0.)if town==1500 else catalog()['towns'][str(town)]['xyz'])
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('UPDATE characters SET level=?WHERE uid=?',(level,uid))
                    db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[level-1],uid))
                values.append(dict(uid=uid,account_id=auth['id'],character_name=name,town=town,auth=auth))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('CREATE TABLE owned_ready_probe(value INTEGER)');db.execute('INSERT INTO owned_ready_probe VALUES(0)')
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for value in values:
                auth=value.pop('auth');value['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
            from els_server.domain.local_session import LocalAccount
            original_getter=LocalAccount.get_inventory_snapshot
            def writer_getter(account):
                actor=app.playing.get(account.account_id)
                if actor is not None and actor.account is account and actor.phase=='square_accepted'and actor.pending_map==1500:
                    try:
                        with closing(sqlite3.connect(cfg.state_file,timeout=.5))as db,db:
                            db.execute('BEGIN IMMEDIATE');db.execute('UPDATE owned_ready_probe SET value=value+1');db.commit();writes.append(account.uid)
                    except sqlite3.Error as error:
                        probe_errors.append(dict(code=getattr(error,'sqlite_errorcode',None),error=repr(error)));raise
                return original_getter(account)
            try:
                with patch.object(LocalAccount,'get_inventory_snapshot',writer_getter):a=await connect(values[0],peers)
            except BaseException:
                if not baseline:raise
                assert probe_errors and probe_errors[-1]['code']==sqlite3.SQLITE_BUSY
                report.update(ok=True,old_ready_reproduced_independent_writer_failure=True)
            else:
                assert not baseline,'Old reader unexpectedly allowed a real repair commit'
                actor=app.playing[values[0]['account_id']];assert actor.phase=='town_ready'and not actor.dungeon_return_pending and writes
                ready=struct.pack('>fffBH',0.,0.,0.,0,0)
                async def expect(peer,kind,body,success=True):
                    answer=await peer.query(kind,body);assert(answer.payload[:4]==bytes(4))==success;return answer
                await expect(a,0x225,struct.pack('>iB',1500,0));before=spa._facts(actor)
                def fail_ready(*args):raise ValueError('Owned late1500ready encoder failure')
                with patch.object(spa,'_ready_reply',fail_ready):await expect(a,0x227,ready,False)
                assert spa._facts(actor)==before and actor.fishing1500_transition['ready']is None
                with patch.object(LocalAccount,'get_inventory_snapshot',writer_getter):await expect(a,0x227,ready)
                count=len(writes);location=actor.account.get_location()
                await expect(a,0x227,ready);assert len(writes)==count and actor.account.get_location()==location
                await expect(a,0x227,struct.pack('>fffBH',1.,0.,0.,0,0),False);assert actor.account.get_location()==location
                low=await connect(values[1],peers);high=await connect(values[2],peers)
                answer=await expect(low,0x225,struct.pack('>iB',1500,1),False)
                assert struct.unpack('>5i',answer.payload)==(518,10,0,0,0)
                answer=await expect(high,0x225,struct.pack('>iB',1500,1),False)
                assert struct.unpack('>5i',answer.payload)==(519,0,30092,0,0)
                assert not errors and not probe_errors,errors
                report.update(ok=True,checks=['Current cold1500ready permits actual independent inventory-repair commits before its location writer',
                    'Late ready encoding leaves location/phase and pending payload unchanged; valid retry commits once, identical replay is stable, changed replay refuses',
                    'Original NPC entry still refuses level9 with level10 requirement and level99 without original30092clear'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(errors=errors,probe_errors=probe_errors,independent_commits=len(writes),fishing_module_sha256=hashlib.sha256(Path(spa.__file__).read_bytes()).hexdigest(),source_sha256={p.relative_to(S).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in S.rglob('*.py')})
    (F/('spa-ready-reader-v2-'+('baseline-'if baseline else'fixed-')+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
