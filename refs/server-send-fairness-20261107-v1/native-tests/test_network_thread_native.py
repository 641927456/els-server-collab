"""Owned Win32 helper: prioritize only the IO loop; workers remain normal."""
import bootstrap,ctypes,json,psutil,sys,threading
from ctypes import wintypes as w
from els_server.__main__ import _normal_scheduling
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.GetCurrentProcess.restype=w.HANDLE;k.GetCurrentThread.restype=w.HANDLE
k.GetThreadPriority.argtypes=[w.HANDLE];k.GetThreadPriority.restype=ctypes.c_int
for name in('SetProcessInformation','GetProcessInformation','GetThreadInformation'):
 f=getattr(k,name);f.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];f.restype=w.BOOL
def memory(thread=False):
 v=w.DWORD();get=k.GetThreadInformation if thread else k.GetProcessInformation
 assert get(k.GetCurrentThread()if thread else k.GetCurrentProcess(),0,ctypes.byref(v),4);return v.value
p=psutil.Process();p.cpu_affinity([20,22]);p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS);p.ionice(psutil.IOPRIO_LOW)
v=w.DWORD(2);assert k.SetProcessInformation(k.GetCurrentProcess(),0,ctypes.byref(v),4)
before=dict(priority_class=int(p.nice()),IO_priority=int(p.ionice()),memory_priority=memory(),thread_priority=k.GetThreadPriority(k.GetCurrentThread()))
assert before==dict(priority_class=16384,IO_priority=1,memory_priority=2,thread_priority=0)
after=_normal_scheduling();assert after==dict(priority_class=32,IO_priority=2,memory_priority=5,network_thread_priority=1)
assert memory(thread=True)==5 and k.GetThreadPriority(k.GetCurrentThread())==1
barrier=threading.Barrier(4);seen=[]
def worker():
 barrier.wait();seen.append(dict(thread_priority=k.GetThreadPriority(k.GetCurrentThread()),memory_priority=memory(True)))
workers=[threading.Thread(target=worker)for _ in range(4)]
for t in workers:t.start()
for t in workers:t.join()
assert seen==[dict(thread_priority=0,memory_priority=5)]*4 and _normal_scheduling()==after
out=dict(ok=True,before=before,after=after,new_workers=seen,main_thread_memory_priority=5,GIL_enabled=sys._is_gil_enabled(),source=bootstrap.SOURCE_BINDINGS,production_process_modified=False,working_set_limits_modified=False)
assert out['GIL_enabled']is False
(bootstrap.HERE/'native-network-thread-priority.json').write_text(json.dumps(out,indent=2),'utf8')
print(json.dumps({k:v for k,v in out.items()if k!='source'}))
