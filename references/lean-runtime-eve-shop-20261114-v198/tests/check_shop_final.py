"""Run the existing shop assertions on the actual installed lean composition."""
from pathlib import Path
import ctypes,hashlib,importlib.util,json,sys,sysconfig
H=Path(__file__).resolve().parent;R=H.parents[1];WORK=H/'checks/shop-final';WORK.mkdir(parents=True,exist_ok=True)
workspace=H/'checks/modules-offline/local-workspace';pointer=json.loads((workspace/'releases/local/current.json').read_bytes());BASE=workspace/pointer['path']
PARENT=R/'analysis/publisher-v197-20261113-v1/runtime'
assert 'sqlite3'not in sys.modules
_sql=ctypes.WinDLL(str(BASE/'python/sqlite3.dll'))
import sqlite3
assert sqlite3.sqlite_version=='3.54.1'and sysconfig.get_config_var('Py_GIL_DISABLED')==1 and not sys._is_gil_enabled()
sys.path[:0]=[str(BASE),str(BASE/'tools')];sys.dont_write_bytecode=True
source=R/'analysis/shop-career-awakening-audit-20261113-v1/repair-v1/check_repair.py';text=source.read_text('utf8')
a=text.index('WORK = ');b=text.index('data = client_data()',a)
header='''WORK=Path(%r)
binding={'parent_release':'latency-attendance-fishing-20261113-v197','files':[{'after_sha256':'d5b4528351fea09a4ab192676299b005e326055f875f3c6bcf6158108fc1653b'}]}
ROOT=Path(%r)
from els_server.game_data import client_data
spec=importlib.util.spec_from_file_location('owned_parent_shop',Path(%r)/'els_server/storage/shop_state.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
'''%(str(WORK),str(BASE),str(PARENT))
text=text[:a]+header+text[b:]
text=text.replace("path = WORK / 'candidate/els_server/storage/shop_state.py'","path = ROOT / 'els_server/storage/shop_state.py'")
text=text.replace("ROOT / 'tools/ed_shop_catalogs.json'","Path("+repr(str(PARENT))+ ") / 'tools/ed_shop_catalogs.json'")
exec(compile(text,str(source),'exec'),dict(__name__='__main__',__file__=str(source)))
assert not sys._is_gil_enabled()
bound={n:str(Path(m.__file__).resolve())for n,m in tuple(sys.modules.items())if(n=='els_server'or n.startswith('els_server.'))and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(BASE)for p in bound.values())
proof=dict(ok=True,actual_installed_lean_runtime=str(BASE),python=sys.version,sqlite=sqlite3.sqlite_version,GIL_enabled=False,source_sha256=hashlib.sha256((BASE/'els_server/storage/shop_state.py').read_bytes()).hexdigest(),original_check_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),client_admission_reused_from_unchanged_native_generation=True,imports=bound)
(WORK/'runtime-binding.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8')
