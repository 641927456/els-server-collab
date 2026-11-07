"""Reuse proved public steps and finish the remaining owned acceptance."""
from common import *
import asyncio,ctypes,datetime,shutil,traceback
held()
old=P/'online-public-acceptance.json';archived=P/'online-public-acceptance-attempt1-midnight.json'
assert not archived.exists();failure=read(old)
assert failure['ok']is False and 'assert saved[:2]==before[:2]and eggs(row[\'alt_items\'])==1'in failure['failure']
assert sha(H/'achievement_spa_client.py')=='255b0caa83eacb91df292046df1162f9d35e715bf9bfcc84f4e0d341bf9c006d'
observed=read(P/'calendar-boundary-observation.json');rows=observed['owned_state']
start=datetime.datetime.fromisoformat(observed['started_utc']).timestamp();day=int(start+28800)//86400
assert [r['play_dates']for r in rows]==[[day],[day,day+1],[day,day+1]]
assert [r['days']for r in rows]==[1,2,2]
assert [r['ED']for r in rows]==[25000000,25000000,24980000]
assert [r['bought']for r in rows]==[0,0,1]and rows[2]['main_eggs']==rows[2]['alt_eggs']==1
shutil.copyfile(old,archived)
source=Path(plan['full_source']);sys.path[:0]=[str(H),str(source),str(source/'vendor'),str(R/'tools/pylibs')]
_sqlite=ctypes.WinDLL(str(source/'python/sqlite3.dll'))
from achievement_spa_resume_client import scenario as spa
from achievement_clear_client import scenario as clear
def snapshot():
    return remote("from pathlib import Path;import subprocess;S=Path("+repr(STAGE)+");q=subprocess.run(['C:/ElsFriends/python/python.exe','-B',str(S/'qa_remote_worker.py'),'snapshot'],cwd='C:/ElsFriends',capture_output=True,timeout=30);assert q.returncode==0,(q.stdout+q.stderr).decode('utf8','replace');print(q.stdout.decode('utf-8-sig'))")

async def main():
    report={k:v for k,v in failure.items()if k not in('failure','ok')}
    report.update(ok=False,resumed_owned_test=True,production_code_changed=False,
        prior_partial_acceptance=dict(path=str(archived),sha256=sha(archived)),
        calendar_boundary_evidence=dict(path=str(P/'calendar-boundary-observation.json'),sha256=sha(P/'calendar-boundary-observation.json')),
        actual_UTC8_midnight_heartbeat_dates_verified=True,inactive_account_kept_one_date=True,
        active_accounts_advanced_once_to_two_dates=True,original_player_databases_restored=False)
    try:
        values=read(P/'qa-credentials.private.json')
        await spa(values,snapshot,report);report['ok']=False
        await clear(values,snapshot,report)
        report.update(connected_source_types=45,connected_definitions=285,remaining_source_types=15,
            unresolved_original_reward_groups=53,new_tables=0,new_indexes=1)
    except BaseException:report.update(ok=False,failure=traceback.format_exc())
    save(P/'online-public-acceptance.json',report);print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
