from pathlib import Path
import argparse,ctypes,gc,hashlib,json,pickle,sys,time
H=Path(__file__).resolve().parent;ROOT=H.parents[1];p=argparse.ArgumentParser();p.add_argument('--parent',action='store_true');a=p.parse_args()
R=ROOT/'analysis/publisher-auth-scope-20261114-v203/runtime/combined'if a.parent else H/'runtime/combined';W=H/('avatar-parent'if a.parent else'avatar-candidate');W.mkdir()
sys.path.insert(0,str(R));sys.path.insert(0,str(R/'tools'))
engine=ctypes.WinDLL(str(R/'python/sqlite3.dll'))
from ctypes import wintypes as T
class MEM(ctypes.Structure):_fields_=[('cb',T.DWORD),('faults',T.DWORD),*[(n,ctypes.c_size_t)for n in('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]]
K=ctypes.WinDLL('kernel32');P=ctypes.WinDLL('psapi');K.GetCurrentProcess.restype=T.HANDLE;P.GetProcessMemoryInfo.argtypes=[T.HANDLE,ctypes.POINTER(MEM),T.DWORD]
def memory():
 m=MEM();m.cb=ctypes.sizeof(m);assert P.GetProcessMemoryInfo(K.GetCurrentProcess(),ctypes.byref(m),m.cb);return m.private
from els_server.domain.selected_2026_pair_runtime import from_pack
from els_server.domain.boosting_2026_chain import ChainGrowthBinding
from els_server.domain.avatar_current_selection_2026 import load_original_metadata
from els_server.domain.avatar_equipped_counts_2026 import count_admitted
manager=from_pack(W/'game.sqlite3',R/'els_server/data/selected2026/local-pair.json')
gc.collect();gc.disable();before=memory();start=time.perf_counter();flows=[manager._growth(lambda s,t:False)for _ in range(100)];elapsed=(time.perf_counter()-start)*1000;after=memory()
catalog=flows[0].avatar
digest=hashlib.sha256(pickle.dumps(catalog,protocol=5)).hexdigest()
assert all(f.avatar==catalog for f in flows)
assert len({id(f.quests)for f in flows})==100 and len({id(f.campaign_open)for f in flows})==100
bad=[]
r=manager.growth_resources
for key in('policy','metadata','definitions','membership','registry'):
 catalogs={k:r['avatar_'+k]for k in('policy','metadata','definitions','membership','registry')};catalogs[key]+=b' '
 try:ChainGrowthBinding(r['growth'],clock=manager.clock,campaign_open=lambda s,t:False,catalogs=catalogs,curve=manager.curve,stats=manager.stats)
 except ValueError:bad.append(key)
 else:raise AssertionError('Changed source accepted '+key)
x=load_original_metadata(r['avatar_metadata']);y=load_original_metadata(r['avatar_metadata']);assert x==y and x is not y
k=next(iter(x));x.pop(k);assert k in y and k in catalog['metadata']
projection=count_admitted(instances=(),selected=(),context2912=0,side=0,membership=catalog['membership'],selector_overrides={},include_flag7=False);assert projection=={}
assert hashlib.sha256(pickle.dumps(catalog,protocol=5)).hexdigest()==digest
out=dict(ok=True,parent=a.parent,constructed=100,elapsed_ms=elapsed,private_delta=after-before,static_catalog_digest=digest,distinct_bundles=len({id(f.avatar)for f in flows}),dynamic_task_and_campaign_objects_independent=True,changed_source_rejected=bad,public_loader_copy_contract_preserved=True,empty_equipment_projection_unchanged=True)
(W/'result.json').write_text(json.dumps(out,indent=2)+'\n','utf8');print(json.dumps(out));gc.enable()
