"""New review cases only: real cross-peer arrival ordering and actual ERP caps."""
from pathlib import Path
from contextlib import closing
import asyncio,json,os,sqlite3,sys,traceback,types,uuid
R=Path(os.environ.get('ELS_WORKSPACE','G:/els'))
N=Path(os.environ.get('ELS_REVIEW_ARTIFACTS',str(R/'analysis/dungeon-result-review-tests-v1')))
N.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('ELS_TEST_ARTIFACTS',str(N/'test-artifacts'))
T=Path(__file__).resolve().parent
sys.path.insert(0,str(T));import verify as v
from els_server.storage.characters import Characters
from els_server.storage import resonance_state as er
from els_server.domain.resonance import limit,experience_multiplier
from els_server.game_data import client_data
from els_server.domain.dungeon_clear import reward_clear_notice


def erp_case(headroom):
    folder=N/'test-artifacts'/('erp-'+uuid.uuid4().hex[:8]);folder.mkdir()
    path=folder/'game.sqlite3'
    from els_server.storage.local_state import ensure_local_tables
    from els_server.storage.reward_state import ensure_reward_tables
    from els_server.storage.inventory_state import ensure_inventory
    with closing(sqlite3.connect(path))as db,db:ensure_local_tables(db);ensure_reward_tables(db);ensure_inventory(db)
    uid=Characters(path,1).create('ERPReview',1,'owned-review-create')['uid']
    full=client_data().thresholds[-1];before=limit()-headroom if headroom is not None else 0
    with closing(sqlite3.connect(path))as db,db:
        db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,));db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(full,uid))
        er.ensure(db);db.execute('INSERT INTO account_resonance VALUES(?,1,?,1)',(1,before))
    helper=v.RulesTests();member=helper.member(uid,own=100)
    plan=v.rules.assess([member],member.reward_run_id)[uid]
    store=v.RewardState(path,uid,account_id=1)
    def grant():return store.grant(plan.run_id,b'owned-original-clear-review',120,50,
        lambda balances,best,effect:reward_clear_notice(effect['ed'],effect['experience'],uid,map_id=30000).payload,
        dungeon_clear=(30000,83),title_economy='clear',dungeon_result=plan,resonance_source='clear',experience_limit=full)
    first=grant();multiplier=experience_multiplier();expected=min(55*multiplier,headroom)if headroom is not None else 55*multiplier
    assert first['resonance_award']['effective']==expected
    assert first['balances']['ed']==132 and first['balances']['experience']==full
    assert v.base.decoded(v.RulesTests.native,first['response'])[0]['experience']==expected
    decision=first['title_economy']['dungeon_result']
    assert decision['ordinary_experience']==0 and decision['resonance_experience']==max(0,expected-50*multiplier)
    second=grant();assert second['replayed']and second['response']==first['response']and store.balances()==first['balances']
    state=er.state(path,uid,1);assert state['experience']==before+expected
    # This fixture contains only our QA role. Connections are closed before it is retired.
    path.unlink();folder.rmdir()
    return dict(passed=True,headroom=headroom,effective_ERP=expected,ordinary_EXP_unchanged=True,ED=132,retry_without_increment=True,fixture_removed=True)


async def interleaved():
    raw=(T/'verify_transport.py').read_text('utf8')
    before="""            for p,wire in zip(peers,wires):await p.send(0x9e,wire);assert(await p.until(0x9f)).payload==bytes(4)
            for p in peers:await p.send(0xbb,bytes(1))
            for p in peers:assert(await p.until(0xbc)).payload==bytes(4)"""
    after="""            for p,wire in zip(peers,wires):
                await p.send(0x9e,wire);assert(await p.until(0x9f)).payload==bytes(4)
                await p.send(0xbb,bytes(1));assert(await p.until(0xbc)).payload==bytes(4)
                if p is alice:
                    assert all(not s.clear_notified for s in sessions), 'First peer must not clear while the other report/BB is pending'"""
    assert raw.count(before)==1;raw=raw.replace(before,after)
    before="""        for p,wire in zip(peers,wires):
            await p.send(0x9e,wire);assert(await p.until(0x9f)).payload==bytes(4)"""
    after="""        sealed=[s.dungeon_result_report for s in sessions]
        for p,wire,actor in zip(peers,wires,sessions):
            altered=base.recipient_report(base.native_report(native,actor.account.uid,(1e30,0,1e30,1e30,0,1e30,0,0),(0,0,0,0),0),{})
            await p.send(0x9e,altered);assert(await p.until(0x9f)).payload==bytes(4)
            assert actor.dungeon_result_report is sealed[sessions.index(actor)], 'Sealed stats changed after clear'"""
    assert raw.count(before)==1;raw=raw.replace(before,after)
    mod=types.ModuleType('review_interleaved_transport');mod.__file__=str(T/'verify_transport.py')
    exec(compile(raw,str(T/'verify_transport.py'),'exec'),mod.__dict__)
    await mod.main()
    result=json.loads((v.ARTIFACTS/'transport-verification-latest.json').read_bytes())
    assert result['passed']and result['owned_service_closed']
    return dict(passed=True,cross_peer_report_BB_interleaved=True,no_premature_shared_clear=True,
        altered_report_after_clear_preserves_sealed_statistics=True,actual_TLS=True,owned_service_closed=True)


if __name__=='__main__':
    report=dict(passed=False,cases=[])
    try:
        v.RulesTests.setUpClass()
        for headroom in(None,510,500,499,0):report['cases'].append(erp_case(headroom))
        report['transport']=asyncio.run(interleaved());report['passed']=True
    except BaseException:report['error']=traceback.format_exc();raise
    finally:
        (N/('review-test-results-'+uuid.uuid4().hex[:8]+'.json')).write_text(json.dumps(report,indent=2)+'\n','utf8')
        (N/'review-test-results.json').write_text(json.dumps(report,indent=2)+'\n','utf8')
        print(json.dumps(dict(passed=report['passed'],new_ERP_cases=len(report['cases']),transport=report.get('transport'))))
