"""Actual invitation commits and real clock crossing on a retained own couple."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'relationship-history-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import relationships,achievements as state,achievement_history as history
from els_server.protocol import relationship_messages as rel,achievement_messages as wire
from els_server.domain.achievement_catalog import points
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data


def retained_couple(db,a,b,stamp):
    """Real proposal/acceptance writer, with an explicitly retained timestamp."""
    au,aa,an=a['uid'],a['account_id'],a['character_name'];bu,ba,bn=b['uid'],b['account_id'],b['character_name']
    grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1)],au)
    guard=lambda db:None
    relationships.propose(db,au,aa,bu,ba,'owned-a','owned-b',rel.descriptor(bn),
        'own-couple-propose:'+str(au),guard=guard,
        encode=lambda left,right,replay,changes:[rel.proposed(right['name'])],now=stamp)
    body=(struct.pack('>bQ',0,au)+rel.wstring(an)+struct.pack('>QBH',0,0,0)+struct.pack('>Q',bu)+rel.wstring(bn)+bytes(1)+rel.descriptor(bn))
    relationships.answer(db,bu,ba,au,aa,'owned-b','owned-a',body,'own-couple-accept:'+str(au),
        guard=guard,encode=lambda left,right,replay,changes:[rel.answered(left,stamp,changes,target_name=right['name'])],now=stamp)


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        production_clock_patch=False,natural_acquisition=False,
        retained_couple_and_nine_request_fixture=True,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-live-social-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for i,letter in enumerate('ABC'):
                auth=app.registry.create('ownedsocialhist'+letter.lower());name='SocHist'+letter
                value=dict(account_id=auth['id'],uid=Characters(cfg.state_file,auth['id']).create(name,i+1,'owned-social-'+letter)['uid'],character_name=name,auth=auth)
                values.append(value)
            uid=[v['uid']for v in values];aid=[v['account_id']for v in values]
            alt=Characters(cfg.state_file,aid[0]).create('SocHistAlt',4,'owned-social-alt')['uid']
            for owner in[*uid,alt]:LocalState(cfg.state_file,owner).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            deadline=int(time.time())+18
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                retained_couple(db,values[0],values[1],deadline-100*86400)
                license=grant_items(db,[dict(template=110845,metadata=0,group=4,quantity=1)],uid[0])[0]
                state.ensure(db)
                for n in range(9):state._save(db,aid[0],uid[0],'duel-invite','0'*64,'own-old-request:'+str(n),dict(target=uid[1],created_at=deadline-100+n))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for value in values:
                auth=value.pop('auth');value['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
                await connect(value,peers)
            a,b,c=peers
            async def request(peer,kind,body=b'',success=True,reply=None):
                answer=await peer.query(kind,body,reply)
                assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:32].hex())
                return answer
            def snapshot(i,owner=None):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,aid[i],uid[i]if owner is None else owner)
            def invitations(i):
                with closing(sqlite3.connect(cfg.state_file))as db:return history.counts(db,aid[i],{29}).get((29,0),0)
            def invite_body(i,j):return struct.pack('>QIQI',uid[i],0,uid[j],0)+rel.wstring(values[i]['character_name'])+bytes(9)
            def notice(peer,start,identity,current):
                fresh=[r for r in current['completed']if r['id']==identity];assert len(fresh)==1
                expected=wire.completion(fresh,points(current['completed']),current['watched'],False).payload
                assert any(e.kind==0x6c0 and e.payload==expected for e in peer.received[start:])
            assert int(time.time())<deadline,'Owned clock fixture must still precede its100day boundary'
            assert all(119 not in{r['id']for r in snapshot(i)['completed']}for i in(0,1))
            await request(a,0x6c1,struct.pack('>i',109))
            starts=[len(p.received)for p in peers]
            actor_type=type(app.playing[aid[0]].account);original_getter=actor_type.get_inventory_snapshot;getter_writes=[]
            def writer_capable_getter(account):
                if account.uid==uid[0]:
                    with closing(sqlite3.connect(cfg.state_file,timeout=1))as probe:
                        probe.execute('BEGIN IMMEDIATE');probe.rollback();getter_writes.append(account.uid)
                return original_getter(account)
            with patch.object(actor_type,'get_inventory_snapshot',writer_capable_getter):
                await request(a,0x5c6,invite_body(0,1))
            await b.until(0x5c8);assert getter_writes
            assert invitations(0)==10 and invitations(1)==invitations(2)==0
            notice(a,starts[0],160,snapshot(0))
            await request(a,0x5c6,invite_body(0,1),False)
            await a.send(0x5cb,b'\0');await a.query(0x48d,reply=0x48f);await b.query(0x48d,reply=0x48f)
            assert invitations(0)==10
            report['checks'].append('Original FullUser inventory getter can acquire its independent SQLite writer before the short journal transaction; ordinary5C6commits the10th request and immediately completes160 only for inviter; pending duplicate fails and cancellation preserves history')
            original=state._save
            def fail_source(db,account,owner,kind,*rest):
                if kind=='duel-invite':raise ValueError('Owned late source-journal failure')
                return original(db,account,owner,kind,*rest)
            start=len(b.received)
            with patch.object(state,'_save',fail_source):await request(c,0x5c6,invite_body(2,1),False)
            await b.query(0x48d,reply=0x48f)
            assert invitations(2)==0 and not any(e.kind==0x5c8 for e in b.received[start:])
            await request(c,0x5c6,invite_body(2,1));await b.until(0x5c8)
            await c.send(0x5cb,b'\0');await c.query(0x48d,reply=0x48f);await b.query(0x48d,reply=0x48f)
            assert invitations(2)==1 and invitations(1)==0
            report['checks'].append('Injected journal failure rolls back and delivers no invitation; next legitimate request succeeds, receiver remains uncredited')
            # Wait for the actual wall clock. No new query supplies counters;
            # the existing periodic path must deliver both completions.
            for peer in(a,b):
                current=snapshot(peers.index(peer))
                if 119 not in{r['id']for r in current['completed']}:await peer.until(0x6c0)
            for i,peer in enumerate((a,b)):
                await peer.query(0x48d,reply=0x48f)
                notice(peer,starts[i],119,snapshot(i))
            assert int(time.time())>=deadline
            assert 119 not in{r['id']for r in snapshot(2)['completed']}
            report['checks'].append('Real wall clock crosses100full days of the explicit retained pair; existing periodic synchronization immediately completes119 for both accounts, without clock patch or new query counters')
            await request(a,0x41a);await request(a,0x41c);await b.query(0x48d,reply=0x48f)
            assert getattr(app.playing[aid[0]],'_achievement_couple_due')is None
            assert getattr(app.playing[aid[1]],'_achievement_couple_due')is None
            assert all(119 in{r['id']for r in snapshot(i)['completed']}for i in(0,1))
            before=snapshot(0);await a.query(0x6be);await a.query(0x6be);assert before==snapshot(0)
            await request(a,0x276,struct.pack('>Q',license['uid'])+rel.wstring('SocDuelProof')+rel.wstring('Owned fixture'))
            with closing(sqlite3.connect(cfg.state_file))as db:guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid[0],)).fetchone()[0]
            await request(a,0x285,rel.wstring(values[1]['character_name'])+struct.pack('>Q',uid[1]));await b.until(0x287)
            await request(b,0x288,struct.pack('>i',guild)+rel.wstring(values[0]['character_name'])+bytes(4))
            for peer in(a,b):
                for kind,body,reply in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),
                    (0x225,struct.pack('>iB',25000,0),0x226),(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
                    await request(peer,kind,body,reply=reply)
            await request(a,0x5c6,invite_body(0,1));await b.until(0x5c8)
            assert invitations(0)==11 and invitations(1)==0
            await a.send(0x5cb,b'\0');await a.query(0x48d,reply=0x48f);await b.query(0x48d,reply=0x48f)
            report['checks'].append('Normal guild create/invite/accept and actual GuildAgit arrival use the same invitation journal; one successful GuildAgit request increments the inviter from10to11 only')
            old=app.playing[aid[0]];await a.close();peers.remove(a)
            async with asyncio.timeout(10):
                while app.playing.get(aid[0])is old:await asyncio.sleep(.02)
            alternate=await connect(dict(values[0],uid=alt,character_name='SocHistAlt'),peers);await alternate.query(0x6be)
            alternate_state=snapshot(0,alt)
            assert {119,160}<={r['id']for r in alternate_state['completed']}
            assert alternate_state['watched']==[]and snapshot(0)['watched']==[109]
            assert invitations(0)==11 and not errors,errors
            report.update(ok=True,checks=[*report['checks'],'Normal free farewell stops active duration scheduling and preserves attained days; repeated queries and cold alternative role restore account history with separate display'],
                actual_invitation_source_commit=True,actual_unpatched_clock_boundary=True)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-social-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
