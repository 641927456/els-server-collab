from common import *
import sys
action=sys.argv[1];held()
if action=='stage':
 assert read(R/'releases/online/current.json')==read(P/'parent.json')
 remote("from pathlib import Path;import json;p=Path("+repr(STAGE)+");assert not p.exists();p.mkdir(parents=True);print(json.dumps(dict(ok=True)))")
 for n in ('requirements.json','runtime-delta.zip','control.py','qa_remote_worker.py','achievement_fixture.py','owned_qa_cleanup.py','shared_snapshot.py'):
  q=transport.scp(P/n,'Administrator@134.175.57.52:'+STAGE+'/'+n);assert q.returncode==0,q.stderr.decode(errors='replace')
 remote("from pathlib import Path;import hashlib,json;S=Path("+repr(STAGE)+");pins="+repr({n:sha(P/n)for n in('requirements.json','runtime-delta.zip','control.py','qa_remote_worker.py','achievement_fixture.py','owned_qa_cleanup.py','shared_snapshot.py')})+";assert all(hashlib.sha256((S/n).read_bytes()).hexdigest()==h for n,h in pins.items());print(json.dumps(dict(ok=True)))")
 owner=dict(owner=OWNER,release=RID,source_head=plan['source_head']);save(P/'stage-owner.json',owner)
 remote("from pathlib import Path;import json;S=Path("+repr(STAGE)+");(S/'stage-owner.json').write_text(json.dumps("+repr(owner)+"),'utf8');print(json.dumps(dict(ok=True)))")
 print(json.dumps(dict(ok=True,staged=True)))
elif action=='start':
 assert read(W/'publication-ready.json')['ok'];assert len(read(P/'requirements.json')['delta'])==8
 task='ELS-Achievement-Guild-Banner-Power-Publication-20261108-v1'
 script="$ErrorActionPreference='Stop';$name='"+task+"';if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'Own task already exists'};$a=New-ScheduledTaskAction -Execute 'C:/ElsFriends/python/python.exe' -Argument '-B \""+STAGE+"/control.py\"' -WorkingDirectory 'C:/ElsFriends';$p=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew;Register-ScheduledTask -TaskName $name -Action $a -Principal $p -Settings $s|Out-Null;Start-ScheduledTask -TaskName $name;[pscustomobject]@{task=$name;state=[string](Get-ScheduledTask -TaskName $name).State}|ConvertTo-Json -Compress"
 save(P/'controller-launch-intent.json',dict(task=task,stage=STAGE,possible_launch=True))
 q=load('dungeon_remote_powershell',R/'tools/remote_windows.py').run(script,timeout=40);assert q.returncode==0,q.stderr.decode('utf8','replace')[-1500:]
 result=json.loads(q.stdout.decode('utf-8-sig'));save(P/'controller-start.json',result);print(json.dumps(result))
elif action=='status':
 v=remote("from pathlib import Path;import json,sys;S=Path("+repr(STAGE)+");sys.path.insert(0,str(S));from shared_snapshot import snapshot;p=S/'journal.json';print(json.dumps(dict(journal=json.loads(snapshot(p))if p.exists()else None,stderr=(S/'control.stderr').read_text('utf8')[-2500:]if(S/'control.stderr').exists()else '')))")
 save(P/'online-journal-readback.json',v);j=v['journal']or{}
 print(json.dumps(dict(journal={k:j[k]for k in('phase','ready','new_pid','observed_seconds','observation_seconds','failure','recovery_error')if k in j},stderr=v['stderr'])))
else:raise ValueError(action)
