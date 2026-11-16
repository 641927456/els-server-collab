"""One ordinary mature-crop harvest crosses a retained-history threshold."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_guild_exit import F,R,B,Application,ServerConfig,GameServer,Characters,LocalState,grant_items,state,history,catalog,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,client_data,wstring,create,connect,notice_ids
from els_server.domain import guild_rules
from els_server.storage import guild_system_state as system
from els_server.protocol.guild_farm_messages import changed
from els_server.domain.guild_farm import empty


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        fixtures=dict(level_ED_license_and_seed=True,retained_harvest_receipts=9,retained_honor=True,maturity_timestamp=True),
        natural_acquisition=False,natural_growth_wait=False,checks=[])
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-live-farm-achievement-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            owners=[app.registry.create('ownedfarmhist'+v)for v in('a','b')]
            names=['FarmHistA','FarmHistB']
            uids=[Characters(cfg.state_file,owner['id']).create(name,index+1,'owned-farm-ach-'+str(index))['uid']for index,(owner,name)in enumerate(zip(owners,names))]
            alt_uid=Characters(cfg.state_file,owners[0]['id']).create('FarmHistAlt',3,'owned-farm-ach-alt')['uid']
            for uid in[*uids,alt_uid]:LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            plant=guild_rules.plants()[min(guild_rules.plants())];seed_template=plant['SEED_ITEM_ID']
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                granted=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)for t in(110845,seed_template)],uids[0])
            license=next(i for i in granted if i['template']==110845);seed=next(i for i in granted if i['template']==seed_template)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            identities=[]
            for owner,uid,name in zip(owners,uids,names):
                identity=dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=owner['name'],token=owner['token'],certificate_sha256=pin))
                identities.append(identity);await connect(identity,peers)
            first,foreign=peers
            async def request(p,kind,body=b'',success=True):
                answer=await p.query(kind,body)
                assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:16].hex())
                return answer
            await request(first,0x276,struct.pack('>Q',license['uid'])+wstring('FarmProof')+wstring('Owned fixture'))
            with closing(sqlite3.connect(cfg.state_file))as db:guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uids[0],)).fetchone()[0]
            await request(first,0x285,wstring(names[1])+struct.pack('>Q',uids[1]));await foreign.query(0x48d,reply=0x48f)
            await request(foreign,0x288,struct.pack('>i',guild)+wstring(names[0])+struct.pack('>i',0))
            for p in peers:
                await request(p,0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000))
                await request(p,0x504,struct.pack('>fffBH',0.,0.,0.,0,0))
            await request(first,0x7fd,struct.pack('>iQ',1,seed['uid']))
            # Only the owned test guild receives these explicit history/time
            # fixtures. Current planting consumed the actual owned seed.
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');saved=system.read(db,guild);plot=saved['plots'][str(uids[0])]['1']
                stamp=int(time.time());plot.update(planted=stamp-plant['TIME']-1,matures=stamp-1);system.write(db,guild,saved)
                for i in range(9):
                    key='owned-retained-harvest-'+str(i);event=changed(0x804,uids[0],1,empty())
                    system.record(db,key,hashlib.sha256(key.encode()).hexdigest(),guild,uids[0],0x803,
                        dict(events=[(event.kind,event.payload.hex())]),stamp-10+i)
                from els_server.storage.guild_quests import record
                earned=dict(guild_rules.calls('SetGuildHonorPoint'))[2]
                assert 0<earned<10000
                record(db,uids[0],'owned-retained-earned-honor',[(100,10000-earned,0)],stamp)
                before_items=db.execute('SELECT COALESCE(SUM(count),0)FROM inventory_items WHERE owner=?AND template=?',(uids[0],plant['RESULT_ITEM_ID'])).fetchone()[0]
                before_money=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uids[0],)).fetchone()
            await first.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert state.snapshot(db,owners[0]['id'],uids[0])['completed']==[]
                assert history.counts(db,owners[0]['id'],{56})[(56,0)]==9
            await request(first,0x803,struct.pack('>i',1))
            with closing(sqlite3.connect(cfg.state_file))as db:
                current=state.snapshot(db,owners[0]['id'],uids[0])
                assert {row['id']for row in current['completed']}=={140,338}
                assert history.counts(db,owners[0]['id'],{56})[(56,0)]==10
                assert history.counts(db,owners[0]['id'],{25})[(25,0)]==10000
                assert db.execute('SELECT COALESCE(SUM(count),0)FROM inventory_items WHERE owner=?AND template=?',(uids[0],plant['RESULT_ITEM_ID'])).fetchone()[0]-before_items==plant['DEFAULT_RESULT_AMOUNT']
                assert db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uids[0],)).fetchone()==before_money
                before=[row for row in db.iterdump()if 'native_achievement_'in row]
            assert [notice_ids(e.payload)for e in first.received if e.kind==0x6c0]==[[140,338]]
            await request(first,0x803,struct.pack('>i',1),False)
            await request(foreign,0x803,struct.pack('>i',1),False)
            for _ in range(2):
                answer=await first.query(0x6c9,struct.pack('>i',338));assert answer.payload[:4]==struct.pack('>i',2005)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert before==[row for row in db.iterdump()if 'native_achievement_'in row]
                assert history.counts(db,owners[1]['id'],{56})[(56,0)]==0
                assert state.snapshot(db,owners[1]['id'],uids[1])['completed']==[]
            await foreign.query(0x48d,reply=0x48f);assert not any(e.kind==0x6c0 for e in foreign.received)
            await first.close();peers.remove(first)
            async with asyncio.timeout(10):
                while owners[0]['id']in app.playing:await asyncio.sleep(.05)
            alt=await connect(dict(identities[0],uid=alt_uid,character_name='FarmHistAlt'),peers);await alt.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert {row['id']for row in state.snapshot(db,owners[0]['id'],alt_uid)['completed']}=={140,338}
            assert not errors,errors
            report.update(ok=True,harvest_template=plant['RESULT_ITEM_ID'],harvest_quantity=plant['DEFAULT_RESULT_AMOUNT'],checks=[
                'Ordinary guild creation/join and4FB/504entry establish the actual two-member GuildAgit',
                'Ordinary7FDplant consumes an owned seed; explicit time fixture makes that same crop mature',
                'Nine retained-receipt fixtures plus one ordinary803harvest complete338once; one plot counts once despite multiple crop items',
                'Actual harvested honor plus the retained earned-honor fixture reaches10000and completes140in the same response',
                'Repeated empty-plot harvest and another member empty-plot request add no progress; no foreign completion notice',
                'Unverified338original reward remains deferred on repeated6C9without a received marker or new progress operation',
                'Alternative-character cold login retains shared farm completion'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-farm-harvest-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
