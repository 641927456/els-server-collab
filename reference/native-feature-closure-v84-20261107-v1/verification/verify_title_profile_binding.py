from pathlib import Path
import hashlib,importlib.util,json,sys,time
I=Path(__file__).resolve().parent;F=I/'full-source';sys.path[:0]=[str(F/'tools'),str(F),str(Path('G:/els/tools/pylibs'))]
p=F/'tools/client_compatibility.py';spec=importlib.util.spec_from_file_location('closure_profile_check',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
report=dict(ok=False,original_client_executable_unchanged=True,guard_relaxed=False,native_Game_created=False)
try:
    result=m.check_client(Path('D:/艾尔之光/data/x2_dx11.exe'),F,emit=lambda line:None)
    report.update(ok=True,profile=result['profile']['id']if isinstance(result.get('profile'),dict)else result.get('profile'),profile_sha256=hashlib.sha256((F/'tools/client_compatibility_profiles.json').read_bytes()).hexdigest())
except BaseException as error:report['error']=repr(error)
out=I/('title-profile-preflight-'+str(time.time_ns())+'.json');out.write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps(report|dict(report=str(out))))
if not report['ok']:raise SystemExit(1)
