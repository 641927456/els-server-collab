"""Real native911 and six-minute observed stay, with an explicit98-grant history."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'social-enhancement-history-v1/delivery-qa'))
from achievement_protocol_client import Peer
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,read_welcome
from els_server.protocol import achievement_messages as wire
from els_server.domain.achievement_catalog import points
from els_server.domain.town_travel import catalog
from els_server.domain import environment_buff_flow as environment
from els_server.storage import achievements as state,achievement_history as history,environment_buffs as buffs
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.game_data import client_data
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from create_friends_certificate import create


def position(town):
    #1500 is an existing measured special scene, outside the ordinary warp catalog.
    #Its saved finite origin is an explicit owned fixture, not native GUI spawning.
    return (0.,0.,0.)if town==1500 else catalog()['towns'][str(town)]['xyz']


async def connect(value,peers):
    p=Peer();p.bridge=Bridge(BridgeConfig(**value['bridge']));p.reader,p.writer=await p.bridge.remote()
    p.keys,p.incoming,p.received=BOOTSTRAP_KEYS,1,[];peers.append(p)
    p.spi,p.keys=read_welcome(await p.until(1));p.outgoing=1
    for kind,reply in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
        await p.send(kind);await p.until(reply)
    town=value['town'];xyz=position(town)
    for kind,reply,body in((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',value['uid'])),(0x6e9,0x6ea,b''),
        (0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),(0x225,0x226,struct.pack('>iB',town,0)),(0x227,0x228,struct.pack('>fffBH',*xyz,0,0))):
        await p.send(kind,body);answer=await p.until(reply)
        if kind in(0x225,0x227):assert answer.payload[:4]==bytes(4)
    await p.query(0x48d,reply=0x48f);return p


async def run():
    continuous_only='--continuous-only'in sys.argv;due_fixture='--due-fixture'in sys.argv
    retained=99 if continuous_only else 98
    report=dict(ok=False,checks=[],production_database_access=False,native_Game=False,natural_GUI=False,
        production_clock_patch=False,production_probability_changed=False,retained_history_fixture=retained,
        diagnostic_due_stay_fixture=due_fixture)
    errors=[];app=server=None;peers=[]
    with tempfile.TemporaryDirectory(prefix='owned-spa-live-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg)
            original_worker=app._worker_call
            def traced_worker(*args,**kwargs):
                try:return original_worker(*args,**kwargs)
                except BaseException as error:
                    report.setdefault('worker_traces',[]).append(dict(method=getattr(args[0],'__qualname__',str(args[0])),
                        code=getattr(error,'sqlite_errorcode',None),name=getattr(error,'sqlite_errorname',None),trace=traceback.format_exc()))
                    raise
            app._worker_call=traced_worker
            await app.start();values=[]
            for index in range(3):
                auth=app.registry.create('ownedspa'+str(index));name='SpaHist'+str(index)
                uid=Characters(cfg.state_file,auth['id']).create(name,index+1,'owned-spa-create:'+str(index))['uid']
                town=1500 if index<2 else 20001
                LocalState(cfg.state_file,uid).save(town,0,0,position(town))
                values.append(dict(uid=uid,account_id=auth['id'],character_name=name,town=town,auth=auth))
            first=values[0];alt=Characters(cfg.state_file,first['account_id']).create('SpaHistAlt',4,'owned-spa-alternative')['uid']
            LocalState(cfg.state_file,alt).save(1500,0,0,position(1500))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                db.execute('UPDATE reward_balances SET ed=0 WHERE uid=?',(values[1]['uid'],))
                for n in range(retained):buffs.put(db,first['uid'],'spa','owned-retained-spa:'+str(n),1700000000+n)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for value in values:
                auth=value.pop('auth');value['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
                await connect(value,peers)
            a,b,c=peers;actor=app.playing[first['account_id']]
            began=actor._spa_stay['start'];assert time.monotonic()-began<30
            def snapshot(value):
                with closing(sqlite3.connect(cfg.state_file))as db:
                    return dict(count=history.counts(db,value['account_id'],{7}).get((7,964),0),
                        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(value['uid'],)).fetchone()[0],
                        achievement=state.snapshot(db,value['account_id'],value['uid']))
            async def purchase(peer,success=True):
                answer=await peer.query(0x911,bytes(4));assert(answer.payload[:4]==bytes(4))==success;return answer
            original=snapshot(first);assert original['count']==retained
            if not continuous_only:
                await purchase(a);after=snapshot(first);assert after['count']==99 and original['ed']-after['ed']==500000
                assert 29 not in{r['id']for r in after['achievement']['completed']}
                assert getattr(actor,'_achievement_spa_source',None)is None
                await purchase(b,False);await purchase(c,False)
                assert snapshot(values[1])['count']==snapshot(values[2])['count']==0
                assert snapshot(values[1])['ed']==0
                before=snapshot(first)
                def fail_encoder(event):raise ValueError('Owned late spa encoder failure')
                with patch.object(environment,'encode_event',fail_encoder):await purchase(a,False)
                assert snapshot(first)==before and getattr(actor,'_achievement_spa_source',None)is None
                with closing(sqlite3.connect(cfg.state_file))as db:
                    operation=db.execute('SELECT operation_id FROM environment_spa_purchases WHERE owner=?',(first['uid'],)).fetchone()[0]
                #Run producer replay through its original application coordinator.
                replay=await app.call(environment._grant,actor,operation,purchase=True)
                assert replay[0].payload[:4]==bytes(4)and snapshot(first)==before
                assert getattr(actor,'_achievement_spa_source',None)is None
                report['checks'].append('Real911 grants/debits once; insufficientED and wrongtown refuse; late encoding failure rolls back buff, journal andED; original producer replay adds nothing')
            else:
                before=original
                report['reused_purchase_proof']='live-spa-1794045544624778400.json; its purchase/rejection/rollback/replay checks succeeded before the later continuous-stay failure'
            if due_fixture:
                for value in values[:2]:app.playing[value['account_id']]._spa_stay['start']-=361
                began=actor._spa_stay['start']
            start=len(a.received);limit=began+390;last_report=0
            while snapshot(first)['count']<100:
                assert time.monotonic()<limit,'Actual owned six-minute grant missed its normal deadline'
                await asyncio.sleep(5)
                for peer in(a,b,c):await peer.query(0x48d,reply=0x48f)
                elapsed=int(time.monotonic()-began)
                if elapsed//60>last_report:last_report=elapsed//60;print('owned-spa-observed-seconds='+str(elapsed),flush=True)
            elapsed=time.monotonic()-began;assert elapsed>=360
            await a.query(0x48d,reply=0x48f);current=snapshot(first)
            assert current['count']==100 and current['ed']==before['ed']
            fresh=[r for r in current['achievement']['completed']if r['id']==29];assert len(fresh)==1
            expected=wire.completion(fresh,points(current['achievement']['completed']),[],False).payload
            assert any(e.kind==0x6c0 and e.payload==expected for e in a.received[start:])
            assert getattr(actor,'_achievement_spa_source',None)is None
            if due_fixture:report['checks'].append('Diagnostic due-stay fixture commits the100th grant; this does not prove a real360-second wait')
            else:
                report['actual_unpatched_continuous_stay_seconds']=elapsed
                report['checks'].append('Real360-second uninterrupted observed spa stay commits the100th grant and immediate29notification without a clock or stay-state patch')
            await a.query(0x6c1,struct.pack('>i',29));before=snapshot(first)
            await a.query(0x6be);await a.query(0x6be);assert snapshot(first)==before
            await a.close();peers.remove(a)
            async with asyncio.timeout(10):
                while app.playing.get(first['account_id'])is actor:await asyncio.sleep(.02)
            alternate=await connect(dict(first,uid=alt,character_name='SpaHistAlt'),peers);await alternate.query(0x6be)
            alt_state=snapshot(dict(first,uid=alt))['achievement']
            assert 29 in{r['id']for r in alt_state['completed']}and alt_state['watched']==[]
            assert snapshot(first)['achievement']['watched']==[29]
            assert snapshot(values[2])['count']==0 and not errors,errors
            report.update(ok=True,checks=[*report['checks'],'Cold alternative role restores account spa history with separate display; repeated reads and foreign account remain stable'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-spa-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
