"""Reuse accepted owned source-loot lifecycle cases against the cumulative runtime."""
import hashlib,json,sys,tempfile,types,unittest
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];R=W/'runtime'
sys.dont_write_bytecode=True;sys.path.insert(0,str(R));tempfile.tempdir=str(W)
old=ROOT/'analysis/legacy-loot-chain-20261019-v2/check_chain.py'
source=old.read_text(encoding='utf8').split("if __name__=='__main__':")[0]
source=source.replace("OUT=Path(__file__).resolve().parent;ROOT=OUT/'candidate';sys.path.insert(0,str(ROOT))",f"OUT=Path({str(old.parent)!r});ROOT=Path({str(R)!r});sys.path.insert(0,str(ROOT))")
# The current production API adds drop_bp; preserve that value while controlling
# only RNG in the same historical issue/pickup fixtures.
source=source.replace("lambda c,b,r:original(c,b,lambda size:next(values))","lambda c,b,r,**kw:original(c,b,lambda size:next(values),**kw)")
source=source.replace("OUT/'inputs/world-drop-probe-snapshot.json'",f"Path({str(ROOT/'analysis/client-6c6b5180/20261014-002737/world-drop-probe-snapshot.json')!r})")
source=source.replace("SimpleNamespace(playing={},accounts={})","SimpleNamespace(playing={},accounts={},world=SimpleNamespace(dungeons=SimpleNamespace(room=lambda s:None)))")
# The former 30282 example now independently requires the bait source's full
# region-qualified lifecycle. 34220 exercises this same normal-loot policy
# without adding an unrelated fishing test to this scope repair.
source=source.replace("((30282,normal.POLICY)","((34220,normal.POLICY)")
source=source.replace("(33031,material.POLICY)","(34330,material.POLICY)")
source=source.replace("            original=storage.issue","            s.handle(Event(0x202,kind=0xffff,payload=b''))\n            original=storage.issue")
source=source.replace("drop=next(d for d in s.world_drops.values() if d['source']==policy)","drop=next((d for d in s.world_drops.values() if d['source']==policy),None);self.assertIsNotNone(drop,(map_id,selected,[(d.get('source'),d['template'])for d in s.world_drops.values()]))")
module=types.ModuleType('historical_loot_chain');module.__file__=str(old)
exec(compile(source,str(old),'exec'),module.__dict__)
names=[
 'test_monster_stones_spawn_pickup_retry_move_and_cold_read',
 'test_inactive_chest_food_is_consumed_once_without_inventory',
 'test_issue_encoding_failure_rolls_back_death_issue_and_memory',
 'test_pickup_encoding_failure_rolls_back_grant_then_can_retry',
 'test_wrong_run_owner_context_and_obsolete_lease_do_not_grant',
 'test_no_drop_and_gate_objects_never_enter_source_admission',
 'test_shared_issue_adapter_preserves_three_existing_loot_policies',
]
label=sys.argv[1]if len(sys.argv)>1 else'first'
if len(sys.argv)>2:names=sys.argv[2:]
with (W/('loot-chain-'+label+'.log')).open('w',encoding='utf8')as log:
 result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.TestSuite(module.Chain(n)for n in names))
out=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),historical_fixture_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),only_fixture_API_change='preserve current drop_bp keyword',current_runtime=str(R),database_directory=str(W),owned_database_removed=not any(W.glob('tmp*')),player_database_opened=False,natural_GUI_or_combat=False)
out['cases']=names;out['fixture_changes']=['preserve current drop_bp keyword','reuse retained native pickup fixture path','complete obsolete-lease empty world fixture','normal-policy example 34220 instead of bait-enabled 30282','material-policy example 34330 instead of separately managed secret 33031','initialize ordinary observers before comparing death/pickup replies']
(W/('loot-chain-'+label+'.json')).write_text(json.dumps(out,indent=2)+'\n',encoding='utf8');print(json.dumps(out));sys.exit(not result.wasSuccessful())
