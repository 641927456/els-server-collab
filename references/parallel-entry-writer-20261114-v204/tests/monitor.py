"""Continuous owned log cursor: preserves enrollment/finish coverage across rotation."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
import ctypes,json,math,os,sys,time,urllib.request
from ctypes import wintypes as W
S=Path(__file__).resolve().parent;R=Path('C:/ElsFriends');sys.path[:0]=[str(S),str(R)]
from els_server.config import ServerConfig
import owned_qa_cleanup as owned
q=owned.read(S/'bindings.json');work=R/'backups'/(q['operation']+'-qa');cfg=ServerConfig.load(R/'config/friends-server.toml')
ids={r['account_id']for r in owned.read(work/'credentials.private.json')};start=owned.read(work/'intent.json')['started_utc'];key=(R/'state/gm/access.key').read_text('ascii').strip()
K=ctypes.WinDLL('kernel32',use_last_error=True);P=ctypes.WinDLL('psapi',use_last_error=True)
K.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];K.OpenProcess.restype=W.HANDLE;K.CloseHandle.argtypes=[W.HANDLE]
class MEM(ctypes.Structure):_fields_=[('cb',W.DWORD),('faults',W.DWORD),*[(n,ctypes.c_size_t)for n in('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]]
P.GetProcessMemoryInfo.argtypes=[W.HANDLE,ctypes.POINTER(MEM),W.DWORD]
K.GetProcessTimes.argtypes=[W.HANDLE,*([ctypes.POINTER(W.FILETIME)]*4)]
handle=K.OpenProcess(0x410,False,q['pid']);assert handle
K.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.LPVOID,W.DWORD,W.DWORD,W.HANDLE];K.CreateFileW.restype=W.HANDLE
def shared_open(path):
 import msvcrt
 h=K.CreateFileW(str(path),0x80000000,7,None,3,0x08000000,None)
 if h==ctypes.c_void_p(-1).value:
  e=ctypes.get_last_error()
  if e in(2,3):raise FileNotFoundError(str(path))
  raise ctypes.WinError(e)
 try:fd=msvcrt.open_osfhandle(h,os.O_RDONLY|os.O_BINARY)
 except BaseException:K.CloseHandle(h);raise
 return os.fdopen(fd,'rb')

def process():
 m=MEM();m.cb=ctypes.sizeof(m);assert P.GetProcessMemoryInfo(handle,ctypes.byref(m),m.cb)
 a,b,c,d=(W.FILETIME()for _ in range(4));assert K.GetProcessTimes(handle,ctypes.byref(a),ctypes.byref(b),ctypes.byref(c),ctypes.byref(d))
 t=lambda x:((x.dwHighDateTime<<32)|x.dwLowDateTime)/1e7
 return dict(cpu_seconds=t(c)+t(d),working_set=m.ws,private_bytes=m.private)
def api():return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18765/api/status',headers={'X-GM-Key':key}),timeout=15))['result']
class Histogram:
 def __init__(self):self.bins=Counter();self.n=0;self.maximum=0.;self.total=0.
 def add(self,x):self.bins[min(60001,max(0,math.ceil(x)))]+=1;self.n+=1;self.maximum=max(self.maximum,x);self.total+=x
 def result(self):
  def p(f):
   n=0
   for b,c in sorted(self.bins.items()):
    n+=c
    if n>=math.ceil(self.n*f):return b
  return dict(n=self.n,p50_ms=p(.5),p95_ms=p(.95),p99_ms=p(.99),max_ms=self.maximum,mean_ms=self.total/self.n if self.n else None)
offsets={};auth={};finished=set();errors=[];hist=defaultdict(Histogram);phase='capacity20';phases={};coverage=False;observations=[];last=0
import psutil
K.GetProcessInformation.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD];K.GetProcessInformation.restype=W.BOOL
K.GetCurrentProcess.restype=W.HANDLE
memory_priority=W.DWORD();assert K.GetProcessInformation(K.GetCurrentProcess(),0,ctypes.byref(memory_priority),4)
priority=dict(priority=int(psutil.Process().nice()),IO_priority=int(psutil.Process().ionice()),memory_priority=memory_priority.value)
assert priority==dict(priority=32,IO_priority=2,memory_priority=5),'Owned observer did not inherit normal scheduling'
owned.write(work/'monitor-ready.json',dict(pid=os.getpid(),started=start,ready_epoch=time.time(),server_pid=q['pid'],owned_accounts=len(ids),continuous_rotation_cursors=True,version=3,priority=priority))
try:
 while not(S/'monitor.stop').exists():
  if(S/'phase.json').exists():phase=owned.read(S/'phase.json')['phase']
  paths=[]
  for p in cfg.log_dir.glob('server.jsonl*'):
   try:paths.append((p.stat().st_mtime,p))
   except FileNotFoundError:pass
  for _,path in sorted(paths,key=lambda pair:pair[0]):
   try:
    if path.suffix!='.jsonl'and not path.suffix[1:].isdigit():continue
    if path.stat().st_mtime<datetime.fromisoformat(start).timestamp():continue
    with shared_open(path)as f:
     st=os.fstat(f.fileno());ino=str(st.st_ino);offset=offsets.get(ino,0)
     if st.st_size<offset:raise RuntimeError('Owned log cursor truncated')
     f.seek(offset)
     while True:
      begin=f.tell();line=f.readline()
      if not line:break
      if not line.endswith(b'\n'):f.seek(begin);break
      offsets[ino]=f.tell()
      try:r=json.loads(line)
      except ValueError:continue
      if r.get('time','')<start:continue
      conn=r.get('connection');event=r.get('event')
      if event=='authenticated'and r.get('account_id')in ids:auth[conn]=r.get('role')
      if event=='connection_finished':finished.add(conn)
      if conn not in auth:continue
      if event in('worker_error','protocol_error','notification_error','connection_task_error'):
       errors.append({k:r[k]for k in('event','time','connection','error')if k in r})
      if event=='request_timing':
       hist[phase,hex(r['kind']),'total_ms'].add(r['total_ms'])
       for call in r.get('calls',[]):
        for k in('queue_ms','worker_cpu_ms','domain_ms','sql_writer_held_ms','world_gate_wait_ms','scope_wait_ms','sql_gate_wait_ms','sql_engine_wait_ms'):
         if k in call:hist[phase,hex(r['kind']),k].add(call[k])
   except FileNotFoundError:
    continue  # Open the renamed generation on the next cursor poll.
  now=time.time()
  if now-last>=2:
   s=api();assert s['ready']and s['owned']and s['pid']==q['pid']
   own=sum(p.get('account_id')in ids for p in s['players']);m=process()
   sample=dict(time=now,phase=phase,own_players=own,total_players=len(s['players']),**m);observations.append(sample)
   if len(observations)>4000:raise RuntimeError('Owned monitor duration bound')
   owned.write(work/'own-log-windows.json',dict(captured_epoch=now,monitor_pid=os.getpid(),coverage_lost=coverage,segment='v3-before-first-owned-authentication',historical_observer_gap=False,owned_auth=len(auth),owned_finished=len(set(auth)&finished),own_errors=errors,roles={str(k):v for k,v in auth.items()},windows=[dict(inode=k,offset=v)for k,v in offsets.items()]))
   owned.write(work/'monitor-progress.json',dict(ok=not errors,server_pid=q['pid'],phase=phase,last=sample,own_authenticated=len(auth),own_finished=len(set(auth)&finished),errors=errors,groups=[dict(phase=p,kind=k,metric=n,**v.result())for(p,k,n),v in hist.items()],observations=observations))
   last=now
  if now-datetime.fromisoformat(start).timestamp()>7200:raise TimeoutError('Owned monitor exceeded two-hour budget')
  time.sleep(.5)
finally:
 K.CloseHandle(handle);owned.write(work/'monitor-closed.json',dict(pid=os.getpid(),coverage_lost=coverage,auth=len(auth),finished=len(set(auth)&finished),own_errors=errors))
