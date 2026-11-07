"""Owned loopback TLS reproduction of online C1 -> delayed AD -> disconnect."""
from pathlib import Path
import argparse,ast,asyncio,hashlib,importlib.util,json,os,sqlite3,struct,sys,tempfile,traceback
from contextlib import closing
W=Path(__file__).resolve().parent;R=Path('G:/els')
args=argparse.ArgumentParser();args.add_argument('--candidate',type=Path);options=args.parse_args()
base=Path(os.environ.get('ELS_CRASH_TEST_RUNTIME',str(R/'releases/online/native-achievement-guild-expedition-history-20261107-v1')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(base),str(base/'tools'),str(R/'tools/pylibs')]
import els_server.domain
if options.candidate:els_server.domain.__path__.insert(0,str(options.candidate/'els_server/domain'))
from els_server.domain import dungeon_settlement_commands as changed
assert Path(changed.__file__).resolve()==((options.candidate or base)/'els_server/domain/dungeon_settlement_commands.py').resolve()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
f=load('owned_current_TLS_fixture',R/'tests/test_friends_server.py')
load('owned_current_continuous_reader',R/'analysis/server-economy-workers-20261102-v1/native_fixture_reader.py').install(f)
load('owned_current_authenticated_frontend',R/'analysis/server-latency-20261106-v7/owned_frontend_client.py').install(f.Peer)
probe=load('owned_existing_death_input',R/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.domain.dungeon_population import population
from els_server.domain.local_session import SessionOrderError
tree=ast.parse((R/'analysis/runtime-latency-online-20261105-v2/live_trial.py').read_bytes())
nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in ('send','admit','emitted_npc')]
assert len(nodes)==3
import math
exec(compile(ast.Module(body=nodes,type_ignores=[]),'existing_protocol_inputs','exec'),globals())
f.Peer.send=send
private=W/'private';private.mkdir(exist_ok=True);tempfile.tempdir=str(private)

def database_snapshot(path):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');return hashlib.sha256('\n'.join(db.iterdump()).encode()).hexdigest()

async def main():
    fixture=f.FriendsTests();await fixture.asyncSetUp()
    result=dict(ok=False,production_changed=False,actual_online_source=str(base),
        candidate=options.candidate is not None,source_sha256=hashlib.sha256(Path(changed.__file__).read_bytes()).hexdigest())
    try:
        peer=await fixture.peer(fixture.alice);await peer.roster()
        uid=fixture.app.accounts[fixture.alice['id']].uid
        stage=await admit(peer,uid,30000)
        late=None
        for index in range(3):
            data=population(index)
            ordered=[n for n in data['npcs']if n['active']and n['key']!=data['clear_key']]+[next(n for n in data['npcs']if n['key']==data['clear_key'])]
            for n in ordered:
                late=probe.accepted_combat(emitted_npc(n,stage),uid)
                await peer.send(0xad,late);assert(await peer.until(0xae)).payload==bytes(4)
            await peer.until(0xba);await peer.send(0xbb,b'\0');assert(await peer.until(0xbc)).payload==bytes(4)
            if index<2:
                stage=await peer.until(0xb2);await peer.send(0xb3,bytes(9));await peer.until(0xbd)
            else:clear=await peer.until(0xc1)
        session=fixture.app.playing[fixture.alice['id']]
        assert session.clear_notified and session._c1_hp_context is not None
        try:session._c1_hp_context.check(None,emitting=True)
        except SessionOrderError:result['HP_lease_still_refuses_after_C1']=True
        else:raise AssertionError('Closed HP context must remain closed')
        before=database_snapshot(fixture.config.state_file)
        await peer.send(0xad,late)
        if options.candidate:
            assert(await peer.until(0xae)).payload==bytes(4)
            assert database_snapshot(fixture.config.state_file)==before
            # Delayed duplicate and summon expiry are acknowledgments only.
            for raw in [late,late[:4]+b'\xff'+late[5:]]:
                await peer.send(0xad,raw);assert(await peer.until(0xae)).payload==bytes(4)
            assert database_snapshot(fixture.config.state_file)==before
            await peer.send(0x48d);await peer.until(0x48f)
            assert fixture.app.playing[fixture.alice['id']]is session
            assert not any(r['event']in('protocol_error','worker_error')for r in fixture.events)
            # Wrong envelope and malformed bytes remain refused, no SQL changes.
            for event in [Event(0x202,kind=0xad,payload=late),Event(0x202,kind=0xad,payload=b'bad',performers=(0,))]:
                assert await fixture.app.call(session.handle,event,request_sequence=10000)==[]
            assert database_snapshot(fixture.config.state_file)==before
            result.update(ok=True,late_AD_acknowledged=True,repeat_and_expiry_ACK_only=True,
                session_kept=True,subsequent_roster_request_passed=True,durable_state_unchanged=True,
                bad_envelope_and_malformed_refused=True)
        else:
            try:await peer.until(0xae)
            except asyncio.IncompleteReadError:pass
            else:raise AssertionError('Expected deployed late AD failure was not reproduced')
            assert any(r['event']=='protocol_error'and r.get('error')=='C1 HP instance lease/phase changed'for r in fixture.events)
            assert database_snapshot(fixture.config.state_file)==before
            result.update(ok=True,reproduced=True,late_AD_after_C1_closes_TLS=True,
                exact_online_error='C1 HP instance lease/phase changed',durable_state_unchanged=True)
        result.update(normal_three_stage_clear=True,C1_bytes=len(clear.payload),natural_GUI=False,natural_combat=False)
        return result
    finally:
        await fixture.asyncTearDown()

if __name__=='__main__':
    name='fixed'if options.candidate else'baseline'
    try:result=asyncio.run(main())
    except BaseException:
        result=dict(ok=False,error=traceback.format_exc());raise
    finally:
        (W/(name+'-TLS-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
        print(json.dumps(result,ensure_ascii=True))
