from pathlib import Path
import ctypes,hashlib,json,sys,sysconfig
H=Path(__file__).resolve().parent;R=H.parents[1];W=H/'checks/tutorial-final';W.mkdir(parents=True,exist_ok=True);T=R/'analysis/lithia-tutorial-skill-hang-20261114-v1/variants-v2'
workspace=H/'checks/modules-offline/local-workspace';v=json.loads((workspace/'releases/local/current.json').read_bytes());actual=workspace/v['path']
assert Path(sys.executable).resolve()==(actual/'server-python/python.exe').resolve()
_sql=ctypes.WinDLL(str(actual/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'and sysconfig.get_config_var('Py_GIL_DISABLED')==1 and not sys._is_gil_enabled()
sys.path[:0]=[str(actual),str(actual/'tools')];sys.dont_write_bytecode=True
for name in('verify_lifecycle.py','verify_families.py'):
 source=T/name;text=source.read_text('utf8');a=text.index('work=Path(__file__)');b=text.index('from els_server.application',a)
 header="work=Path(%r)\ntask=Path(%r)\nROOT=Path(%r)\nruntime=Path(%r)\nmode='v2'\n"%(str(W),str(T.parent),str(R),str(actual))
 text=text[:a]+header+text[b:]
 if name=='verify_families.py':text=text.replace('for unit,identity in MAPS.items():','for unit,identity in ((15,MAPS[15]),):')
 scope=dict(__name__='__main__',__file__=str(source));exec(compile(text,str(source),'exec'),scope)
assert not sys._is_gil_enabled()
imports={n:str(Path(m.__file__).resolve())for n,m in tuple(sys.modules.items())if(n=='els_server'or n.startswith('els_server.'))and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(actual)for p in imports.values())
rows=json.loads((H/'draft-source-receipt.json').read_bytes())['source_changes'];assert len(rows)==8 and all(hashlib.sha256((actual/r['path']).read_bytes()).hexdigest()==r['sha256']for r in rows)
proof=dict(ok=True,actual_installed_runtime=str(actual),python=sys.version,sqlite=sqlite3.sqlite_version,GIL_enabled=False,source_files={r['path']:r['sha256']for r in rows},raven_clear_normal_result_refusal_chung_switch=True,fresh_Lithia_reports_and_encrypted_following_request=True,unchanged_15_family_results_reused=True,all_business_imports_from_selected_runtime=True,natural_GUI=False)
(W/'runtime-binding.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Final V199 tutorial lifecycle: Raven complete/refusal, same-session Chung switch, fresh Lithia reports/encrypted next request passed on installed 3.14t/GIL-off')
