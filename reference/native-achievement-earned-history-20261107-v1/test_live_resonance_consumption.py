"""Ordinary TLS allocation/refund, scroll and mentor-blessing achievement paths."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_guild_exit import F,R,B,Application,ServerConfig,GameServer,Characters,LocalState,grant_items,state,history,catalog,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,client_data,create,connect,notice_ids
from els_server.domain.resonance_allocation_flow import definitions
from els_server.storage.resonance_state import ensure as ensure_resonance


def allocation(delta):return struct.pack('>IBIiiB',1,0,1,1,delta,1)


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        fixtures=dict(level_ED_opened_ERP150_and_consumables=True),natural_acquisition=False,checks=[])
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-live-erp-consumption-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            owners=[app.registry.create('ownedconsumption'+v)for v in('a','b')];names=['UseHistA','UseHistB']
            uids=[Characters(cfg.state_file,o['id']).create(n,i+1,'owned-use-'+str(i))['uid']for i,(o,n)in enumerate(zip(owners,names))]
            alt_uid=Characters(cfg.state_file,owners[0]['id']).create('UseHistAlt',3,'owned-use-alt')['uid']
            for uid in[*uids,alt_uid]:LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                ensure_resonance(db)
                db.executemany('INSERT INTO account_resonance VALUES(?,1,?,1)',[(o['id'],definitions()[0].threshold(150))for o in owners])
                granted=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)for t,n in((710106,100),(163564,5))],uids[0])
                # Explicit owned fixture uses the exact mentor reward vector
                # and original source validator; no natural task claim credit.
                from els_server.domain import mentor_quests as mentor_rules
                from els_server.domain.raid_reward_items import _issue_source
                stamp=int(time.time());plan=mentor_rules.reward_plan(45001,stamp)
                def fixture_guard(writer):
                    return writer is db and writer.execute('SELECT account_id FROM character_owners WHERE uid=?',(uids[0],)).fetchone()==(owners[0]['id'],)
                for i in range(5):
                    identity=dict(policy=mentor_rules.POLICY,owner=uids[0],quest=45001,at=stamp,cycle=i,definition_sha256=mentor_rules.DATA_SHA)
                    source=_issue_source(db,uids[0],'owned-mentor-item-fixture-'+str(i),'ordinary',identity,plan,fixture_guard)
                    granted+=grant_items(db,plan,uids[0],raid_reward_source=source)
                foreign=grant_items(db,[dict(template=712417,metadata=VERIFIED_TEMPLATES[712417],group=TEMPLATE_BAG_GROUPS[712417],quantity=1)],uids[1])[0]
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest();identities=[]
            for owner,uid,name in zip(owners,uids,names):
                identity=dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=owner['name'],token=owner['token'],certificate_sha256=pin))
                identities.append(identity);await connect(identity,peers)
            first,second=peers
            def saved(account=0,uid=None):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,owners[account]['id'],uids[account]if uid is None else uid)
            baseline={r['id']for r in saved()['completed']}
            async def request(peer,kind,body,success=True):
                answer=await peer.query(kind,body)
                assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:28].hex())
                return answer
            await request(first,0x611,allocation(100));await request(first,0x611,allocation(-100))
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert history.counts(db,owners[0]['id'],{43})[(43,0)]==100
                assert db.execute('SELECT COALESCE(SUM(count),0)FROM inventory_items WHERE owner=?AND template=710106',(uids[0],)).fetchone()==(0,)
            await request(first,0x611,allocation(-1),False)
            for _ in range(5):
                await request(first,0x611,allocation(1));await request(first,0x613,bytes((0,1)))
            await request(first,0x613,bytes((0,1)),False)
            for _ in range(5):
                with closing(sqlite3.connect(cfg.state_file))as db:
                    source_uid=db.execute('SELECT uid FROM inventory_items WHERE owner=?AND template=189800 ORDER BY slot LIMIT 1',(uids[0],)).fetchone()[0]
                await request(first,0x718,struct.pack('>QiB',source_uid,2,1))
            await request(first,0x718,struct.pack('>QiB',source_uid,2,1),False)
            await request(second,0x718,struct.pack('>QiB',foreign['uid'],2,1))
            expected={78,80,81,82,83,84,299,300}
            assert {r['id']for r in saved()['completed']}==baseline|expected
            notices=[i for e in first.received if e.kind==0x6c0 for i in notice_ids(e.payload)]
            assert len(notices)==len(set(notices))and set(notices)==expected,notices
            with closing(sqlite3.connect(cfg.state_file))as db:
                counts=history.counts(db,owners[0]['id'],{16,43,44})
                assert counts=={(16,189800):5,(43,0):100,(44,0):5},counts
                assert history.counts(db,owners[1]['id'],{16,43,44})=={(16,189800):0,(43,0):0,(44,0):0}
                assert not db.execute('SELECT 1 FROM inventory_items WHERE owner=?AND template IN(710106,163564,189800)',(uids[0],)).fetchone()
                before=[r for r in db.iterdump()if 'native_achievement_'in r]
            await first.query(0x6be);await first.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert before==[r for r in db.iterdump()if 'native_achievement_'in r]
            assert not expected&{r['id']for r in saved(1)['completed']}
            await request(first,0x6c1,struct.pack('>i',299));await first.close();peers.remove(first)
            async with asyncio.timeout(10):
                while owners[0]['id']in app.playing:await asyncio.sleep(.05)
            alt=await connect(dict(identities[0],uid=alt_uid,character_name='UseHistAlt'),peers);await alt.query(0x6be)
            assert {r['id']for r in saved(0,alt_uid)['completed']}==baseline|expected
            assert saved(0,alt_uid)['watched']==[]and saved()['watched']==[299]
            assert not errors,errors
            report.update(ok=True,actual_counts={str(k):v for k,v in counts.items()},checks=[
                'Ordinary611allocates100and refunds100with exactly100owned710106coins; an over-refund fails without another debit or count',
                'Five ordinary positive category613refunds consume five163564scrolls and complete80through84; an empty category retry fails',
                'Five ordinary718mentor189800uses consume five actual owned units, complete299and300once; a missing source retry fails',
                'Another account successfully uses712417without increasing source16or receiving these completions',
                'Repeated6BEreads add no progress; alternative-character cold login shares completions and keeps its display list separate'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-resonance-consumption-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
