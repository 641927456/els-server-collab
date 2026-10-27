import ctypes,subprocess
from ctypes import wintypes as W
K=ctypes.WinDLL('kernel32',use_last_error=True);U=ctypes.WinDLL('user32',use_last_error=True)
class STARTUPINFO(ctypes.Structure):
 _fields_=[('cb',W.DWORD),('lpReserved',W.LPWSTR),('lpDesktop',W.LPWSTR),('lpTitle',W.LPWSTR),('dwX',W.DWORD),('dwY',W.DWORD),('dwXSize',W.DWORD),('dwYSize',W.DWORD),('dwXCountChars',W.DWORD),('dwYCountChars',W.DWORD),('dwFillAttribute',W.DWORD),('dwFlags',W.DWORD),('wShowWindow',W.WORD),('cbReserved2',W.WORD),('lpReserved2',ctypes.c_void_p),('hStdInput',W.HANDLE),('hStdOutput',W.HANDLE),('hStdError',W.HANDLE)]
class PROCINFO(ctypes.Structure):_fields_=[('hProcess',W.HANDLE),('hThread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
assert ctypes.sizeof(STARTUPINFO)==104 and ctypes.sizeof(PROCINFO)==24
for name,restype,args in [('GetCurrentThreadId',W.DWORD,[]),('GetCurrentProcessId',W.DWORD,[]),('CloseHandle',W.BOOL,[W.HANDLE]),('ResumeThread',W.DWORD,[W.HANDLE]),('WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD]),('TerminateProcess',W.BOOL,[W.HANDLE,W.UINT]),('GetExitCodeProcess',W.BOOL,[W.HANDLE,ctypes.POINTER(W.DWORD)]),('CreateProcessW',W.BOOL,[W.LPCWSTR,W.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,W.BOOL,W.DWORD,ctypes.c_void_p,W.LPCWSTR,ctypes.POINTER(STARTUPINFO),ctypes.POINTER(PROCINFO)])]:
 f=getattr(K,name);f.restype=restype;f.argtypes=args
for name,restype,args in [('GetProcessWindowStation',W.HANDLE,[]),('GetThreadDesktop',W.HANDLE,[W.DWORD]),('GetUserObjectInformationW',W.BOOL,[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.POINTER(W.DWORD)]),('OpenInputDesktop',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD]),('CloseDesktop',W.BOOL,[W.HANDLE]),('CreateDesktopW',W.HANDLE,[W.LPCWSTR,W.LPCWSTR,ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.c_void_p]),('SetThreadDesktop',W.BOOL,[W.HANDLE]),('OpenDesktopW',W.HANDLE,[W.LPCWSTR,W.DWORD,W.BOOL,W.DWORD])]:
 f=getattr(U,name);f.restype=restype;f.argtypes=args

def check(value):
 if not value:raise ctypes.WinError(ctypes.get_last_error())
 return value

def object_name(handle):
 buf=ctypes.create_unicode_buffer(512);size=W.DWORD();check(U.GetUserObjectInformationW(handle,2,buf,ctypes.sizeof(buf),ctypes.byref(size)));return buf.value

def input_desktop():
 h=check(U.OpenInputDesktop(0,False,1))
 try:return object_name(h)
 finally:check(U.CloseDesktop(h))

def spawn(args,desktop,cwd,suspended=False):
 si=STARTUPINFO();si.cb=ctypes.sizeof(si);si.lpDesktop=desktop;si.dwFlags=1;si.wShowWindow=4;pi=PROCINFO();cmd=ctypes.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in args]));flags=0x08000200|(4 if suspended else 0);check(K.CreateProcessW(str(args[0]),cmd,None,None,False,flags,None,str(cwd),ctypes.byref(si),ctypes.byref(pi)));return pi

def exit_code(pi):
 out=W.DWORD();check(K.GetExitCodeProcess(pi.hProcess,ctypes.byref(out)));return out.value

def close_process(pi):check(K.CloseHandle(pi.hThread));check(K.CloseHandle(pi.hProcess))
