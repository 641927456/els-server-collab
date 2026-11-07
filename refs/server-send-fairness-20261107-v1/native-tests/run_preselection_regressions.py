"""Rerun only admission/shared dispatch and town delivery affected by queue routing."""
import json,subprocess,time
from pathlib import Path
H=Path(__file__).resolve().parent;FT=Path('G:/els/releases/online/native-writer-checkpoints-20261107-v1/server-python/python.exe')
rows=[]
for name in('test_solo_routing_native.py','run_current_member_checks.py','test_peer_window_native.py'):
 start=time.perf_counter()
 with(H/('preselection-'+name+'.private.log')).open('xb')as log:
  code='import sys,runpy;sys.path.insert(0,'+repr(str(H))+');runpy.run_path('+repr(str(H/name))+",run_name='__main__')"
  result=subprocess.run([str(FT),'-B','-X','utf8','-c',code,'--candidate'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=240)
 rows.append(dict(test=name,exit_code=result.returncode,seconds=time.perf_counter()-start))
 (H/'preselection-affected-regressions.json').write_text(json.dumps(rows,indent=2),'utf8')
 print(json.dumps(rows[-1]),flush=True)
 if result.returncode:raise RuntimeError('Affected native regression failed: '+name)
