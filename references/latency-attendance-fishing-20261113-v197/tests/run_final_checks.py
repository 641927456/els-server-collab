"""Run affected existing assertions against final signed leaves, without overlays."""
from pathlib import Path
import ctypes,hashlib,json,os,runpy,sys,sysconfig,tempfile,types
H=Path(__file__).resolve().parent;R=H.parents[1];FINAL=H/'runtime';OUT=H/'integration-checks';OUT.mkdir(exist_ok=True)
mode=sys.argv[1];args=sys.argv[2:]
BASE=Path(args.pop(0))if mode=='recovery-fishing'else FINAL
assert 'sqlite3'not in sys.modules
_sqlite_runtime=ctypes.WinDLL(str(BASE/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'
assert sysconfig.get_config_var('Py_GIL_DISABLED')==1 and not sys._is_gil_enabled()
sys.dont_write_bytecode=True;os.environ.update(TEMP=str(OUT),TMP=str(OUT),PYTHONDONTWRITEBYTECODE='1');tempfile.tempdir=str(OUT)
sys.path[:0]=[str(R/'analysis/town-dungeon-latency-20261105-v6/free-thread-deps'),str(BASE),str(BASE/'vendor'),str(R),str(R/'tools'),str(R/'tools/pylibs'),str(R/'tools/launcher_testdeps')]
import els_server.application,els_server.transport,els_server.friends_bridge
assert not sys._is_gil_enabled()
if mode=='public':
    runpy.run_path(str(H/'verify_public_flow.py'),run_name='__main__')
elif mode=='perf':
    source=R/'analysis/live-town-quest-latency-20261113-v6'
    boot=types.ModuleType('bootstrap');boot.HERE=OUT;boot.ROOT=R;boot.BASE=BASE;boot.FREE_THREADED_BUILD=True
    boot.SOURCE_BINDINGS={r['path']:r['sha256']for r in json.loads((H/'composition.json').read_bytes())['files']}
    sys.modules['bootstrap']=boot
    sys.path[:0]=[str(source),str(R/'analysis/server-latency-20261106-v7')]
    sys.argv=[str(source/args[0]),'--candidate'];runpy.run_path(sys.argv[0],run_name='__main__')
elif mode in ('fishing','recovery-fishing'):
    source=R/'analysis/fishing-live-audit-20261113-v1/repair-v1/verify.py'
    text=source.read_text('utf8')
    text=text.replace('HERE=Path(__file__).resolve().parent;ROOT=Path(\'G:/els\')',"HERE=Path("+repr(str(OUT))+ ");ROOT=Path('G:/els')")
    text=text.replace("BASE=ROOT/'releases/online/third-job-skill-slots-20261113-v196';CANDIDATE=HERE/'candidate'","BASE=Path("+repr(str(BASE))+");CANDIDATE=HERE/'no-overlay'")
    text=text.replace("if MODE=='recovery':CANDIDATE=HERE/'recovery'","if MODE=='recovery':CANDIDATE=HERE/'no-overlay'")
    sys.argv=[str(source),'recovery'if mode=='recovery-fishing'else'new',*args]
    exec(compile(text,str(source),'exec'),dict(__name__='__main__',__file__=str(source)))
elif mode=='career':
    source=R/'analysis/third-job-skill-slots-20261113-v1/check_server.py'
    text=source.read_text('utf8');a=text.index('WORK = ');b=text.index('from els_server.config',a)
    text=text[:a]+"WORK=Path("+repr(str(OUT))+")\nROOT=Path('G:/els')\nBASE=Path("+repr(str(BASE))+")\n"+text[b:]
    sys.argv=[str(source),'--candidate','quest'];exec(compile(text,str(source),'exec'),dict(__name__='__main__',__file__=str(source)))
else:raise ValueError(mode)
assert not sys._is_gil_enabled()
imports={n:str(Path(m.__file__).resolve())for n,m in tuple(sys.modules.items())if(n=='els_server'or n.startswith('els_server.'))and getattr(m,'__file__',None)}
assert imports and all(Path(p).is_relative_to(BASE)for p in imports.values()),'Mixed runtime imports'
(OUT/(mode+'-final-runtime.json')).write_text(json.dumps(dict(ok=True,runtime=sys.version,sqlite=sqlite3.sqlite_version,GIL_enabled=False,imports=imports),indent=2),'utf8')
