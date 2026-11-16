"""Committed fishing journal and ordinary expedition completion achievement sources."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback,uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_profiles import W,Application,ServerConfig,GameServer,Characters,LocalState,create,catalog,connect,records,state
from els_server.storage import fishing_attempt,pet_expedition,companion_state,pet_progression,life_stamina,game_mail
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.pet_progression import template,threshold
from els_server.storage.achievement_history import counts
from els_server.storage.achievement_profiles import reconcile
from els_server.domain import achievement_flow
from els_server.protocol import fishing_messages as fishing_wire
from els_server.protocol.local_messages import wstring


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        retained_journal_rows_are_fixtures=True,natural_fishing_timer=False,natural_expedition_wait=False,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-life-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();ident=app.registry.create('ownedachlife');foreign=app.registry.create('ownedachlifeforeign')
            uid=Characters(cfg.state_file,ident['id']).create('AchLifeA',1,'owned-life-create-A')['uid']
            other=Characters(cfg.state_file,foreign['id']).create('AchLifeB',1,'owned-life-create-B')['uid']
            for value in(uid,other):LocalState(cfg.state_file,value).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            now=int(time.time())
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
                db.execute('UPDATE reward_balances SET ed=6000000 WHERE uid=?',(uid,))
                sources=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)
                    for t,n in((135928,1),(99809,2),(500051,1))],uid)
                fishing_attempt.ensure(db);pet_expedition.ensure(db)
                # Boundary setup is explicitly synthetic. The last fishing
                # attempt and expedition completion use their real writers.
                db.executemany('INSERT INTO fishing_attempts VALUES(?,?,?,?,?,?,?,?,?,?)',
                    [(ident['id'],uid,'owned-history-fishing',n,'owned-history-fishing-'+str(n),'{}',now-1000+n,0,None,4800)for n in range(999)])
                db.execute('INSERT INTO fishing_attempts VALUES(?,?,?,?,?,?,?,?,?,?)',(foreign['id'],other,'owned-foreign-fishing',0,'owned-foreign-fishing-0','{}',now,1,135933,4800))
                db.executemany('INSERT INTO pet_expedition_receipts VALUES(?,?,?,?,?,?)',
                    [('owned-exp-history-'+str(n),uid,ident['id'],'complete','fixture','{}')for n in range(9)]+
                    [('owned-exp-not-complete-'+action,uid,ident['id'],action,'fixture','{}')for action in('start','cancel')]+
                    [('owned-exp-foreign',other,foreign['id'],'complete','fixture','{}')])
                initial=counts(db,ident['id'],{61,62,63});assert initial=={(61,0):999,(63,0):9},initial
            egg=next(i for i in sources if i['template']==500051)
            companion_state.handle(cfg.state_file,uid,0x2e8,struct.pack('>Q',egg['uid'])+wstring('AchLifePet'),'owned-life-pet',account_id=ident['id'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');pet=companion_state.rows(db,uid,'pet')[0]
                pet['step']=template(pet['unit'])['EVOLUTION_ALL_STEP'];pet['growth']=threshold(pet)
                pet['personality']={str(k):0 for k in range(4)};pet_progression.save(db,uid,pet)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            first=await connect(dict(uid=uid,character_name='AchLifeA',bridge=dict(host='127.0.0.1',port=port,name=ident['name'],token=ident['token'],certificate_sha256=pin)),peers)
            await first.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert not state.snapshot(db,ident['id'],uid)['completed']
            live=app.playing[ident['id']]
            guard=lambda db:life_stamina.owner(db,uid,ident['id'])
            # Exercise the actual settlement writer with current owned gear,
            # one bait debit, durability debit, life debit and golden catch.
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE')
                for item in sources:
                    if item['template']in(135928,99809):
                        db.execute('UPDATE inventory_items SET bag_group=?,slot=0 WHERE owner=?AND uid=?',(22 if item['template']==135928 else 23,uid,item['uid']))
                db.execute('UPDATE location SET town=1500 WHERE uid=?',(uid,))
            cycle,_=fishing_attempt.start(cfg.state_file,uid,ident['id'],live.shop_session_id,lambda *args:[],guard,now=lambda:now-40)
            result=fishing_attempt.settle(cfg.state_file,uid,ident['id'],live.shop_session_id,cycle['cycle'],0,
                lambda caught,used,changes,life,notices:[fishing_wire.attempt_notice(0,caught=caught,consumed=used,changes=changes)],
                guard,now=lambda:now,randbelow=lambda n:0)
            assert not result['replayed']
            with closing(sqlite3.connect(cfg.state_file))as db:before_replay=list(db.iterdump())
            assert fishing_attempt.settle(cfg.state_file,uid,ident['id'],live.shop_session_id,cycle['cycle'],0,
                lambda *args:[],guard,now=lambda:now)['replayed']
            with closing(sqlite3.connect(cfg.state_file))as db:assert before_replay==list(db.iterdump())
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE location SET town=20001 WHERE uid=?',(uid,))
            with app.world_lock:
                notices=achievement_flow.synchronize(live,None,result['reply'])
                for event in notices:live.mailbox.append(event)
            await first.query(0x48d,reply=0x48f)
            assert [[r['id']for r in records(e.payload)[0]]for e in first.received if e.kind==0x6c0]==[[363,366]]
            with closing(sqlite3.connect(cfg.state_file))as db:
                before=list(db.iterdump());value=counts(db,ident['id'],{61,62,63})
                assert value=={(61,0):1000,(62,135933):1,(63,0):9},value
                assert before==list(db.iterdump())
            # The ordinary expedition request performs the tenth committed
            # complete action, after only its saved deadline is advanced here.
            with closing(sqlite3.connect(cfg.state_file))as db:mission=db.execute('SELECT mission FROM pet_expedition_runs WHERE owner=?',(uid,)).fetchone()[0]
            answer=await first.query(0x8c1,struct.pack('>iiIQ',1,mission,1,pet['uid']),0x8c2);assert answer.payload[:4]==bytes(4)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE pet_expedition_runs SET ends_at=?WHERE owner=?',(now-1,uid))
            answer=await first.query(0x8c3,struct.pack('>ii',1,mission),0x8c4);assert answer.payload[:4]==bytes(4)
            assert [[r['id']for r in records(e.payload)[0]]for e in first.received if e.kind==0x6c0]==[[363,366],[367]]
            answer=await first.query(0x8c3,struct.pack('>ii',1,mission),0x8c4);assert answer.payload[:4]!=bytes(4)
            await first.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');before=list(db.iterdump())
                assert reconcile(db,ident['id'],uid,now)==dict(completed=[],replayed=False)
                assert counts(db,ident['id'],{61,62,63})=={(61,0):1000,(62,135933):1,(63,0):10}
                assert {r['id']for r in state.snapshot(db,ident['id'],uid)['completed']}=={363,366,367}
                assert before==list(db.iterdump())
            # The ambiguous original golden-catch potion stays deferred.
            for _ in range(2):
                answer=await first.query(0x6c9,struct.pack('>i',366),0x6ca)
                assert answer.payload[:4]==struct.pack('>i',2005)and answer.payload[-1:]==b'\0'
            assert game_mail.inbox(cfg.state_file,ident['id'],uid)==(0,[])
            assert sum(e.kind==0x6c0 for e in first.received)==2
            assert not errors,errors
            report.update(ok=True,completed=[363,366,367],checks=[
                '999retained attempt fixtures include misses; a real fishing settlement debits owned bait/durability/life, catches135933and completes363/366once through actual source synchronization',
                'Nine retained completed-expedition fixtures exclude start/cancel/foreign records; ordinary8C1then8C3 completes367once after explicit deadline fixture',
                'Repeated8C3without an active run is rejected; unchanged reconciliation is read-only and no extra completion is sent',
                'Ambiguous original366reward is rejected twice without mail or a received marker'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    (W/('fishing-expedition-sources-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
