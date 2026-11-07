"""Retained real receipts plus ordinary live trade/mail complete both social sources."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_profiles import W,Application,ServerConfig,GameServer,Characters,LocalState,create,catalog,connect,records,state
from combined_qa_client import mail_request
from els_server.storage import player_trade_state as trades,player_mail,game_mail
from els_server.storage.achievement_history import counts
from els_server.storage.achievement_profiles import reconcile
from els_server.protocol import player_trade_messages as trade_wire,player_mail_messages as mail_wire
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.bank_rules import player_ed_limit


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        retained_receipts_from_real_storage_writers=True,historical_multiplayer_GUI=False,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-history-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            owners=[app.registry.create('ownedachhist'+suffix)for suffix in('a','b','c')]
            uids=[Characters(cfg.state_file,owner['id']).create('AchHist'+suffix.upper(),i+1,'own-history-'+suffix)['uid']for i,(owner,suffix)in enumerate(zip(owners,('a','b','c')))]
            for uid in uids:LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE reward_balances SET ed=?',(player_ed_limit(1)//4,))
            agreement=dict(participants=[dict(owner=uid,account=owner['id'],ed=1 if i==0 else 0,items=[])for i,(uid,owner)in enumerate(zip(uids,owners))if i<2])
            def encode_trade(db,results,replayed):
                for result in results.values():encode_event(trade_wire.completed(result['ed'],result['changes']))
                return dict(replayed=replayed)
            for n in range(49):
                result=trades.perform(cfg.state_file,agreement,'owned-historical-trade-'+str(n),lambda db,now:None,encode_trade)
                assert not result['replayed']
            request=dict(recipient='AchHistB',title='Owned history',body='Private fixture',ed=0,item=0,count=0,flag=0,extra=0)
            def encode_mail(result):
                message=Event(0x201,kind=0x1d0,payload=mail_wire.send_ack(result['ed'],result['recipient']))
                encode_event(message);return[message]
            for n in range(4):player_mail.send(cfg.state_file,owners[0]['id'],uids[0],request,'owned-historical-mail-'+str(n),encode_mail)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert counts(db,owners[0]['id'],{27,28})=={(27,0):49,(28,0):4}
                assert counts(db,owners[1]['id'],{27,28})=={(27,0):49,(28,0):0}
                assert counts(db,owners[2]['id'],{27,28})=={(27,0):0,(28,0):0}
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for uid,owner,suffix in zip(uids[:2],owners[:2],('A','B')):
                await connect(dict(uid=uid,character_name='AchHist'+suffix,bridge=dict(host='127.0.0.1',port=port,name=owner['name'],token=owner['token'],certificate_sha256=pin)),peers)
            for peer in peers:await peer.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert all(state.snapshot(db,owner['id'],uid)['completed']==[]for uid,owner in zip(uids,owners))
                plan=' '.join(str(row)for row in db.execute("EXPLAIN QUERY PLAN SELECT COUNT(*)FROM native_player_trades WHERE json_extract(ledger_json,'$[0].account')=?OR json_extract(ledger_json,'$[1].account')=?",(owners[0]['id'],owners[0]['id'])))
                assert 'native_achievement_trade_account_a'in plan and 'native_achievement_trade_account_b'in plan
            first,second=peers
            assert(await first.query(0x174,struct.pack('>Q',uids[1]),0x175)).payload[:4]==bytes(4)
            await second.query(0x48d,reply=0x48f)
            assert any(e.kind==0x176 for e in second.received)
            await second.query(0x177,struct.pack('>QBi',uids[0],1,0),0x179)
            await first.query(0x48d,reply=0x48f)
            assert(await first.query(0x182,struct.pack('>Q',10),0x183)).payload[:4]==bytes(4)
            for peer in peers:assert(await peer.query(0x185,reply=0x186)).payload[:4]==bytes(4)
            for peer in peers:assert(await peer.query(0x188,reply=0x189)).payload[:4]==bytes(4)
            for peer in peers:await peer.query(0x48d,reply=0x48f)
            assert all(sum(e.kind==0x18b for e in peer.received)==1 for peer in peers)
            for peer in peers:
                notices=[records(e.payload)[0]for e in peer.received if e.kind==0x6c0]
                assert [[r['id']for r in rows]for rows in notices]==[[150]]
            answer=await first.query(0x1cf,mail_request('AchHistB',0,0),0x1d0)
            assert answer.payload[:4]==bytes(4)
            first_notices=[records(e.payload)for e in first.received if e.kind==0x6c0]
            assert [[r['id']for r in rows]for rows,_ in first_notices]==[[150],[155]]
            assert first_notices[-1][1]==[0,0,20,0]
            with closing(sqlite3.connect(cfg.state_file))as db:
                before=list(db.iterdump())
            assert trades.perform(cfg.state_file,agreement,'owned-historical-trade-0',lambda db,now:None,encode_trade)['replayed']
            with closing(sqlite3.connect(cfg.state_file))as db:assert before==list(db.iterdump())
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');before=list(db.iterdump())
                assert reconcile(db,owners[0]['id'],uids[0],int(time.time()))==dict(completed=[],replayed=False)
                assert before==list(db.iterdump())
                assert counts(db,owners[0]['id'],{27,28})=={(27,0):50,(28,0):5}
                assert {r['id']for r in state.snapshot(db,owners[0]['id'],uids[0])['completed']}=={150,155}
                assert {r['id']for r in state.snapshot(db,owners[1]['id'],uids[1])['completed']}=={150}
                assert state.snapshot(db,owners[2]['id'],uids[2])['completed']==[]
            assert game_mail.inbox(cfg.state_file,owners[1]['id'],uids[1])[0]==5
            for identity_value in(150,155):
                for _ in range(2):
                    ack=await first.query(0x6c9,struct.pack('>i',identity_value),0x6ca)
                    assert ack.payload[:4]==bytes(4)and ack.payload[-1:]==b'\1'
            assert game_mail.inbox(cfg.state_file,owners[1]['id'],uids[1])[0]==5
            assert game_mail.inbox(cfg.state_file,owners[0]['id'],uids[0])==(0,[])
            assert not errors,errors
            report.update(ok=True,completed_sender=[150,155],completed_trade_peer=[150],
                checks=['49real committed storage trades and4real ordinary send receipts backfill below their thresholds; foreign account counts remain0',
                'Both expression indexes are used for account trade history',
                'Ordinary174/177/182/185/188personal trade completes50th; both caller and mailbox recipient get one6C0',
                'Ordinary1CF/1D0 fifth mail completes155once; no client counter input',
                'Old trade receipt replay changes no database state; unchanged source projection writes nothing',
                'Repeated no-reward claims create no mail; five actual recipient mails retain their original ownership'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in peers:
                try:await peer.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={str(p.relative_to(W/'source-v1')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'source-v1').rglob('*')if p.is_file()and '__pycache__'not in p.parts}
    (W/('social-history-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
