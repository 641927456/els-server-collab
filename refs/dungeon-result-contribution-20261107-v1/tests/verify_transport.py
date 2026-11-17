"""Two real authenticated peers, original shared admission and three-part clear.

Death inputs and9E counters are explicit protocol QA inputs, not natural combat.
No room/run/clear flag is forced; the real clear writer must commit both actors.
"""
from pathlib import Path
from contextlib import closing
import ast,asyncio,hashlib,json,math,sqlite3,ssl,struct,sys,traceback,uuid
from verify import HERE,R,RUNTIME,base,rules,decoded,ARTIFACTS
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.game_data import client_data
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.domain.dungeon_population import population
from create_friends_certificate import create

def load(name,path):
    import importlib.util
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
f=load('local_result_native_peer',R/'tests/test_friends_server.py')
tree=ast.parse((R/'analysis/runtime-latency-online-20261105-v2/live_trial.py').read_bytes())
nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in('send','emitted_npc')]
assert len(nodes)==2
exec(compile(ast.Module(body=nodes,type_ignores=[]),'qualified-original-protocol-inputs','exec'),globals())
f.Peer.send=send
load('local_result_original_reader',R/'analysis/server-economy-workers-20261102-v1/native_fixture_reader.py').install(f)
load('local_result_original_frontend',R/'analysis/server-latency-20261106-v7/owned_frontend_client.py').install(f.Peer)
probe=load('local_result_death_inputs',R/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')

async def main():
    attempt=ARTIFACTS/('tls-'+uuid.uuid4().hex[:10]);attempt.mkdir();private=attempt/'private'
    pin=create(private,'127.0.0.1')
    cfg=ServerConfig(port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
        tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=attempt/'logs',friends_coop_enabled=True)
    app=Application(cfg);server=None;peers=[];bridges=[];errors=[]
    evidence=dict(passed=False,natural_battle=False,natural_GUI=False,production_mutation=False,
        original_shared_admission=True,room_or_clear_forced=False,protocol_death_inputs=True,marker_statistics=True)
    try:
        await app.start();identities=[]
        for n in range(2):
            account=app.registry.create('contributionqa'+str(n));name='ResultRule'+str(n)
            uid=Characters(cfg.state_file,account['id']).create(name,1,'owned-local-rule-create-'+str(n))['uid']
            LocalState(cfg.state_file,uid).save(20000,0,0,(1.,2.,3.))
            QuestState(cfg.state_file,uid,account_id=account['id']).snapshot()
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=10,revision=revision+1 WHERE uid=?',(uid,))
                db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[9],uid))
                db.executemany('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',[(uid,q,1,'{}')for q in(26660,26680)])
            identities.append(dict(account=account,uid=uid,name=name))
        def log(event,**kw):
            if event in('worker_error','notification_error','connection_task_error'):errors.append(dict(event=event,**kw))
        server=GameServer(cfg,app,log);_,port=await server.start()
        for identity in identities:
            bridge=Bridge(BridgeConfig('127.0.0.1',port,identity['account']['name'],identity['account']['token'],pin));bridges.append(bridge)
            peer=await f.Peer.open(bridge);peers.append(peer);await peer.roster()
            await peer.enter_town(identity['uid'],town=20000)
        alice,bob=peers;a,b=(i['uid']for i in identities)
        await alice.invite(bob,b,identities[1]['name'],a)
        await bob.send(0x14c,b'\1'+bytes(4))
        for peer in peers:await peer.until(0x14d)
        await alice.send(0x7d4,struct.pack('>ii',1,30000));assert(await alice.until(0x7d5)).payload[:4]==bytes(4)
        await alice.send(0x382,probe.ENTRY);assert(await alice.until(0x383)).payload[:4]==bytes(4)
        admissions=[await p.until(0x14a)for p in peers];assert admissions[0].payload==admissions[1].payload
        for p in peers:await p.send(0x91,struct.pack('>ii',100,0))
        stages=[await p.until(0xb2)for p in peers]
        sessions=[app.playing[i['account']['id']]for i in identities]
        assert all(s.dungeon_result_power[0]==s.account.uid for s in sessions)
        evidence['admitted_power']=[s.dungeon_result_power[1]for s in sessions]
        native=base.Replay()
        wires=[base.recipient_report(base.native_report(native,a,(1000,800,200,700,600,100,50,40),(100,80,30,20),44),{b:3.5}),
               base.recipient_report(base.native_report(native,b,(4000,3000,1000,3000,2200,800,250,80),(500,300,100,50),123),{a:7.5})]
        for index in range(3):
            for p in peers:await p.send(0xb3,bytes(9))
            for p in peers:await p.until(0xbd)
            data=population(index)
            ordered=[n for n in data['npcs']if n['active']and n['key']!=data['clear_key']]+[next(n for n in data['npcs']if n['key']==data['clear_key'])]
            for npc in ordered:
                await alice.send(0xad,probe.accepted_combat(emitted_npc(npc,stages[0]),a));assert(await alice.until(0xae)).payload==bytes(4)
            for p in peers:await p.until(0xba)
            for p,wire in zip(peers,wires):await p.send(0x9e,wire);assert(await p.until(0x9f)).payload==bytes(4)
            for p in peers:await p.send(0xbb,bytes(1))
            for p in peers:assert(await p.until(0xbc)).payload==bytes(4)
            if index<2:stages=[await p.until(0xb2)for p in peers]
        results=[await p.until(0xc1)for p in peers]
        rows=[decoded(native,e.payload)for e in results]
        details=[base.decoded(native,e.payload)for e in results]
        assert rows[0]==rows[1]and details[0]==details[1]
        assert [r['uid']for r in rows[0]]==[a,b]
        assert [r['mvp']for r in rows[0]]==[0,1]
        assert all(r['rank']in range(1,9)for r in rows[0])
        assert [r['values']['0xfe']for r in details[0]]==[1000,4000]
        assert [r['values']['0x160']for r in details[0]]==[7.5,3.5]
        cold=[]
        with closing(sqlite3.connect(cfg.state_file))as db:
            for s,row,detail in zip(sessions,rows[0],details[0]):
                raw=db.execute('SELECT effect_json FROM reward_title_receipts WHERE run_id=?',(s.reward_run_id,)).fetchone()[0]
                effect=json.loads(raw);decision=effect['dungeon_result']
                assert decision['rank']==row['rank']and int(decision['mvp'])==row['mvp']
                assert decision['awards']==[bool(v)for v in row['awards']]
                assert abs(row['contribution']-decision['score_bp']/100)<.001
                assert decision['applied_ed']in(0,12)
                assert detail['ed']==effect['ed']==decision['base_ed']+decision['applied_ed']
                assert detail['experience']==effect['experience']
                if decision['bonus_bp']:
                    assert decision['ordinary_experience']>0
                else:assert decision['ordinary_experience']==0
                cold.append(dict(rank=row['rank'],score_bp=decision['score_bp'],MVP=decision['mvp'],awards=decision['awards'],
                    base_ed=decision['base_ed'],bonus_ed=decision['applied_ed'],bonus_experience=decision['ordinary_experience'],
                    C1_ED=detail['ed'],C1_experience=detail['experience']))
            before=db.execute('SELECT uid,ed,experience,revision FROM reward_balances ORDER BY uid').fetchall()
        for p,wire in zip(peers,wires):
            await p.send(0x9e,wire);assert(await p.until(0x9f)).payload==bytes(4)
            await p.send(0xbb,bytes(1));assert(await p.until(0xbc)).payload==bytes(4)
        with closing(sqlite3.connect(cfg.state_file))as db:
            assert db.execute('SELECT uid,ed,experience,revision FROM reward_balances ORDER BY uid').fetchall()==before
        assert not errors,errors
        evidence.update(passed=True,rows=rows[0],cold=cold,retry_without_increment=True,errors=errors)
    except BaseException:evidence.update(error=traceback.format_exc(),errors=errors);raise
    finally:
        for peer in reversed(peers):await peer.close()
        for bridge in reversed(bridges):await bridge.close()
        if server is not None:await server.close()
        app.close();evidence['owned_service_closed']=True
        (attempt/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
        (ARTIFACTS/'transport-verification-latest.json').write_text(json.dumps(dict(attempt=str(attempt),**evidence),indent=2)+'\n')
        print(json.dumps({k:v for k,v in evidence.items()if k not in('error','rows','cold')}))

if __name__=='__main__':asyncio.run(main())
