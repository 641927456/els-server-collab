import ctypes,sys
from ctypes import wintypes as W
from pathlib import Path
R=Path('G:/els');sys.path.insert(0,str(R/'analysis/local-activities-20261017-v85/research/background-backend-v1'));from desktop_api import K,U,check,object_name,input_desktop,spawn,exit_code,close_process,STARTUPINFO,PROCINFO
class BASIC(ctypes.Structure):
 _fields_=[('ProcessTime',ctypes.c_longlong),('JobTime',ctypes.c_longlong),('Flags',W.DWORD),('MinWS',ctypes.c_size_t),('MaxWS',ctypes.c_size_t),('Active',W.DWORD),('Affinity',ctypes.c_size_t),('Priority',W.DWORD),('Scheduling',W.DWORD)]
class IO(ctypes.Structure):_fields_=[('rOp',ctypes.c_ulonglong),('wOp',ctypes.c_ulonglong),('oOp',ctypes.c_ulonglong),('rBytes',ctypes.c_ulonglong),('wBytes',ctypes.c_ulonglong),('oBytes',ctypes.c_ulonglong)]
class EXT(ctypes.Structure):_fields_=[('Basic',BASIC),('IO',IO),('ProcessMemory',ctypes.c_size_t),('JobMemory',ctypes.c_size_t),('PeakProcessMemory',ctypes.c_size_t),('PeakJobMemory',ctypes.c_size_t)]
assert ctypes.sizeof(BASIC)==64 and ctypes.sizeof(EXT)==144
for name,ret,args in [('CreateJobObjectW',W.HANDLE,[ctypes.c_void_p,W.LPCWSTR]),('SetInformationJobObject',W.BOOL,[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD]),('QueryInformationJobObject',W.BOOL,[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.c_void_p]),('AssignProcessToJobObject',W.BOOL,[W.HANDLE,W.HANDLE]),('IsProcessInJob',W.BOOL,[W.HANDLE,W.HANDLE,ctypes.POINTER(W.BOOL)]),('GetCurrentProcess',W.HANDLE,[])]:
 f=getattr(K,name);f.restype=ret;f.argtypes=args
def create_job(name):
 h=check(K.CreateJobObjectW(None,name));ext=EXT();ext.Basic.Flags=0x2000
 try:check(K.SetInformationJobObject(h,9,ctypes.byref(ext),ctypes.sizeof(ext)));ui=W.DWORD(0xff);check(K.SetInformationJobObject(h,4,ctypes.byref(ui),4));return h
 except BaseException:K.CloseHandle(h);raise
def job_limits(h=None):
 ui=W.DWORD();ext=EXT();check(K.QueryInformationJobObject(h,4,ctypes.byref(ui),4,None));check(K.QueryInformationJobObject(h,9,ctypes.byref(ext),ctypes.sizeof(ext),None));return dict(ui_flags=ui.value,limit_flags=ext.Basic.Flags,breakaway_allowed=bool(ext.Basic.Flags&0x1800))
def job_pids(h):
 b=ctypes.create_string_buffer(8+16*8);check(K.QueryInformationJobObject(h,3,b,len(b),None));import struct
 assigned,listed=struct.unpack_from('<II',b);assert listed<=16;return dict(assigned=assigned,listed=listed,pids=list(struct.unpack_from('<'+'Q'*listed,b,8)),raw_prefix=bytes(b)[:8+listed*8].hex())
