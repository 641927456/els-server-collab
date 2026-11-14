from common import *
held();r=read(H/'steady20/result.json');assert r['ok']and r['steady_seconds']>=1800 and r['actors']==r['peak_connections']==20 and r['connections_drained']
S='C:/ElsFriends-staging/'+RID;W='C:/ElsFriends/backups/'+RID+'-qa'
code=f'''from pathlib import Path
import json,subprocess,time
S=Path({S!r});W=Path({W!r})
for _ in range(30):
 d=json.loads((W/'own-log-windows.json').read_bytes())
 if time.time()-d['captured_epoch']<20 and d['owned_auth']==d['owned_finished']:break
 time.sleep(.5)
else:raise RuntimeError('Owned authentication/finish sequence has not drained')
p=subprocess.run(['C:/ElsFriends/server-python/python.exe','-B',str(S/'qa_worker.py'),'cold'],cwd='C:/ElsFriends',capture_output=True,timeout=120);assert p.returncode==0,(p.stdout+p.stderr).decode('utf8','replace')[-1200:]
print(json.dumps(dict(cold=json.loads(p.stdout.decode('utf-8-sig')),monitor=json.loads((W/'monitor-progress.json').read_bytes()),windows=d,ready=json.loads((W/'monitor-ready.json').read_bytes()))))
'''
d=remote(code);save(H/'final-capacity-readback.private.json',d)
assert d['windows']['owned_auth']==d['windows']['owned_finished']==r['expected_game_authentications']
assert r['network_path']['mode']=='per_socket_physical_interface'and not r['network_path']['global_route_changed']and r['all_sockets_bound_to_physical_source']
assert r['physical_connections']==r['successful_physical_connections']==r['expected_game_authentications']
assert not d['windows']['own_errors']and not d['windows']['coverage_lost']and not d['windows']['historical_observer_gap']
actual={str(x['uid']):x['delta']for x in d['cold']['balances']};assert actual==r['expected_ED']
groups={g['kind']:g for g in d['monitor']['groups']if g['metric']=='total_ms'}
for kind in('0x485','0x28','0x227','0x91','0xb3','0xad','0xd0','0xb8','0xbb'):
 assert groups[kind]['n']==r['samples'][kind]['n'],(kind,groups[kind]['n'],r['samples'][kind]['n'])
assert d['ready']['ready_epoch']<r['steady_started_epoch']and d['ready']['version']==3
observations=d['monitor']['observations'];steady=[x for x in observations if r['steady_started_epoch']<=x['time']<=r['steady_started_epoch']+1800]
assert len(steady)>300 and max(b['time']-a['time']for a,b in zip(steady,steady[1:]))<20
acceptance=dict(ok=True,installed_release=read(H/'baseline.json')['currents']['online']['release'],actual_server_PID=d['monitor']['server_pid'],actors=20,requested_steady_seconds=1800,actual_steady_seconds=r['steady_seconds'],public_TLS=True,natural_twenty_GUI_clients=False,normal_admission=True,original_emitted_HP_and_issued_ED=True,forced_server_room=False,counts=r['counts'],game_authentications=r['expected_game_authentications'],all_connections_drained=True,all_owned_authentication_and_finish_events_accounted=True,all_target_server_timing_counts_equal_client_counts=True,full_monitor_coverage=True,all_cold_ED_equal_acknowledged_pickups=True,server_errors=0,client_latencies=r['samples'],server_groups=d['monitor']['groups'],observed_CPU_cores=(steady[-1]['cpu_seconds']-steady[0]['cpu_seconds'])/(steady[-1]['time']-steady[0]['time']),peak_private_bytes=max(x['private_bytes']for x in steady),peak_working_set=max(x['working_set']for x in steady),sampled_players=dict(min=min(x['own_players']for x in steady),max=max(x['own_players']for x in steady)),observed_total_players=dict(min=min(x['total_players']for x in steady),max=max(x['total_players']for x in steady)),resource_metrics_cover_whole_server_process=True,planned_room_reconnections=True,source_runtime_pinned=read(H/'online-baseline.json')['source_pins'],result_sha256=sha(H/'steady20/result.json'),network_path=r['network_path'],physical_connections=r['physical_connections'],all_sockets_bound_to_physical_source=True)
save(H/'capacity-acceptance.json',acceptance)
save(H/'capacity-outcome.json',dict(acceptance,accepted=True,attempt_completed=True))
print(json.dumps(dict(ok=True,actors=20,seconds=r['steady_seconds'],counts=r['counts'],game_authentications=r['expected_game_authentications'],all_server_target_timing_counts_accounted=True,all_cold_ED_equal=True)))
