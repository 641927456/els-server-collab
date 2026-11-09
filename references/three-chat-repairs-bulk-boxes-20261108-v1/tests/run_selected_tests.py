"""Run retained relevant tests against actual assembly-selected components."""
from pathlib import Path
import ctypes,hashlib,json,os,runpy,shutil,sys,sysconfig,tempfile,types
H=Path(__file__).resolve().parent;R=Path('G:/els');mode=sys.argv[1];read=lambda p:json.loads(Path(p).read_bytes());B=Path(read(H/'launcher-preview-v114/built-selection-verification.json')['selected_root']);out=H/'selected-tests'/mode;out.mkdir(parents=True,exist_ok=True)
assert 'sqlite3'not in sys.modules
runtime=ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'
sys.dont_write_bytecode=True;os.environ.update(TEMP=str(out),TMP=str(out),PYTHONDONTWRITEBYTECODE='1');tempfile.tempdir=str(out)
sys.path[:0]=[str(B),str(B/'vendor'),str(R/'analysis/town-dungeon-latency-20261105-v6/free-thread-deps'),str(B/'tools'),str(R/'tools'),str(B/'tools/pylibs'),str(R/'tools/pylibs'),str(R/'tools/launcher_testdeps'),str(R/'analysis/server-latency-20261106-v7')]
bindings={r['path']:r['sha256']for r in read(H/'candidate.json')['files']}
for name,pin in bindings.items():assert hashlib.sha256((B/name).read_bytes()).hexdigest()==pin
stub=types.ModuleType('bootstrap');stub.HERE=out;stub.OUT=out;stub.ROOT=R;stub.BASE=B;stub.SOURCE_BINDINGS=bindings;stub.FREE_THREADED_BUILD=sysconfig.get_config_var('Py_GIL_DISABLED')==1
sys.modules['bootstrap']=stub
import els_server.domain,els_server.storage,els_server.protocol
from els_server.domain.owned_growth_items import install
install()
from els_server.domain.abyss_weapon_2026 import register
register()
if mode=='pet':
 original=R/'analysis/pet-auto-cooldown-20261108-v1/verify.py';source=original.read_text('utf8');start=source.index('OUT=Path(__file__)');end=source.index('from els_server.domain.local_session',start)
 source=source[:start]+"OUT=Path("+repr(str(out))+");ROOT=Path('G:/els');BASE=Path("+repr(str(B))+")\n"+source[end:]
 sys.argv=[str(original)];namespace=dict(__name__='selected_pet_qualified',__file__=str(original));exec(compile(source,str(original),'exec'),namespace)
 import unittest
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(namespace['PetCooldownTests']);result=unittest.TextTestRunner(verbosity=2).run(suite);assert result.wasSuccessful()and result.testsRun==4
elif mode in('giant','burst'):
 folder=R/'analysis/plegas-consumables-20261108-v1'if mode=='giant'else R/'analysis/manual-potion-response-20261108-v1/independent-lane'
 sys.path.insert(0,str(folder))
 if(folder/'fixture-shape.json').exists():shutil.copyfile(folder/'fixture-shape.json',out/'fixture-shape.json')
 script=folder/('verify_consumables.py'if mode=='giant'else'verify_burst.py');sys.argv=[str(script),'--candidate'];runpy.run_path(str(script),run_name='__main__')
elif mode=='boxes':
 folder=R/'analysis/stackable-box-final-20261108-v1/local-policy-v1';sys.path.insert(0,str(folder));stub.Path=Path;stub.json=json;stub.sys=sys
 sys.argv=[str(folder/'verify_local_rules.py')]
 try:runpy.run_path(str(folder/'verify_local_rules.py'),run_name='__main__')
 except SystemExit as exit:
  if exit.code not in(0,None):raise
else:raise ValueError(mode)
record=dict(ok=True,mode=mode,actual_selected_root=str(B),runtime=sys.version,SQLite=sqlite3.sqlite_version,GIL_enabled=sys._is_gil_enabled(),source_bindings=bindings,source_binding_count=len(bindings),natural_GUI=False,own_isolated_tests=True)
(out/'selected-runtime.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf8');assert stub.FREE_THREADED_BUILD and not record['GIL_enabled'];print(json.dumps(dict(ok=True,mode=mode,source_files=len(bindings),GIL_enabled=False)))
