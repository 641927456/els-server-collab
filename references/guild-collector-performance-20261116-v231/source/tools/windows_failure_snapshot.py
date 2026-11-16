"""Read-only failure snapshot in a disposable, time-bounded helper process.

No privilege adjustment, thread suspension, remote call or process termination.
Only this helper is stopped by the caller's timeout. Object names are excluded.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys


def emit(value):
    print(json.dumps(value, separators=(',', ':')), flush=True)


def capture(pid, created, preferred_thread=0):
    if os.name != 'nt':
        emit(dict(stage='identity', status='not_windows'));return
    sys.path.insert(0, str(Path(__file__).parent/'pylibs'))
    import psutil
    process = psutil.Process(pid)
    if abs(process.create_time()-created) > .001:
        emit(dict(stage='identity', status='creation_time_mismatch'));return
    k = C.WinDLL('kernel32', use_last_error=True)
    a = C.WinDLL('advapi32', use_last_error=True)
    k.OpenProcess.argtypes = [W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE];k.CloseHandle.restype=W.BOOL
    k.GetProcessTimes.argtypes=[W.HANDLE,*([C.POINTER(W.FILETIME)]*4)];k.GetProcessTimes.restype=W.BOOL
    k.GetProcessMitigationPolicy.argtypes=[W.HANDLE,C.c_int,C.c_void_p,C.c_size_t];k.GetProcessMitigationPolicy.restype=W.BOOL
    a.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)];a.OpenProcessToken.restype=W.BOOL
    a.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)];a.GetTokenInformation.restype=W.BOOL
    a.GetSidSubAuthorityCount.argtypes=[C.c_void_p];a.GetSidSubAuthorityCount.restype=C.POINTER(C.c_ubyte)
    a.GetSidSubAuthority.argtypes=[C.c_void_p,W.DWORD];a.GetSidSubAuthority.restype=C.POINTER(W.DWORD)
    def security(handle):
        result={};credential=W.HANDLE()
        if not a.OpenProcessToken(handle,8,C.byref(credential)):
            return dict(status='unavailable',winerror=C.get_last_error())
        try:
            size=W.DWORD();elevated=W.DWORD()
            if a.GetTokenInformation(credential,20,C.byref(elevated),C.sizeof(elevated),C.byref(size)):
                result['elevated']=bool(elevated.value)
            else:result['elevation_winerror']=C.get_last_error()
            a.GetTokenInformation(credential,25,None,0,C.byref(size))
            if not 0<size.value<=4096:
                result['integrity_winerror']=C.get_last_error();return result
            label=C.create_string_buffer(size.value)
            if a.GetTokenInformation(credential,25,label,size,C.byref(size)):
                sid=C.cast(label,C.POINTER(C.c_void_p))[0]
                count=a.GetSidSubAuthorityCount(sid)[0]
                if count:result['integrity_rid']=a.GetSidSubAuthority(sid,count-1)[0]
            else:result['integrity_winerror']=C.get_last_error()
            return result
        finally:k.CloseHandle(credential)
    handle=k.OpenProcess(0x1000,False,pid)
    if not handle:
        emit(dict(stage='identity',status='open_failed',winerror=C.get_last_error()));return
    try:
        times=[W.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle,*[C.byref(v) for v in times]):
            emit(dict(stage='identity',status='times_unavailable',winerror=C.get_last_error()));return
        actual=((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)/10000000-11644473600
        if abs(actual-created)>.001:
            emit(dict(stage='identity',status='handle_creation_time_mismatch'));return
        emit(dict(stage='identity',status='matched',process_id=pid,process_created=actual))
        result=dict(stage='security',target=security(handle),mitigations={})
        own=k.OpenProcess(0x1000,False,os.getpid())
        if own:
            try:result['collector']=security(own)
            finally:k.CloseHandle(own)
        else:result['collector']=dict(status='unavailable',winerror=C.get_last_error())
        for name,policy in [('dynamic_code',2),('extension_points',6),('binary_signature',8),('image_load',10)]:
            flags=W.DWORD()
            result['mitigations'][name]=(dict(flags=flags.value) if k.GetProcessMitigationPolicy(handle,policy,C.byref(flags),C.sizeof(flags))
                                         else dict(status='unavailable',winerror=C.get_last_error()))
        emit(result)
        # A successful identity check does not pin the PID after exit; recheck
        # before and after WCT, and invalidate the sample if the process changed.
        threads=process.threads();ids=[v.id for v in threads]
        if preferred_thread in ids:ids.remove(preferred_thread);ids.insert(0,preferred_thread)
        class Lock(C.Structure):
            _fields_=[('name',W.WCHAR*128),('timeout',C.c_longlong),('alertable',W.BOOL)]
        class Thread(C.Structure):
            _fields_=[('pid',W.DWORD),('tid',W.DWORD),('wait_time',W.DWORD),('switches',W.DWORD)]
        class Details(C.Union):_fields_=[('lock',Lock),('thread',Thread)]
        class Node(C.Structure):_fields_=[('kind',C.c_int),('status',C.c_int),('details',Details)]
        if C.sizeof(Node)!=280:raise RuntimeError('Unexpected WCT node layout')
        a.OpenThreadWaitChainSession.argtypes=[W.DWORD,C.c_void_p];a.OpenThreadWaitChainSession.restype=W.HANDLE
        a.CloseThreadWaitChainSession.argtypes=[W.HANDLE];a.CloseThreadWaitChainSession.restype=None
        a.GetThreadWaitChain.argtypes=[W.HANDLE,C.c_size_t,W.DWORD,W.DWORD,C.POINTER(W.DWORD),C.POINTER(Node),C.POINTER(W.BOOL)]
        a.GetThreadWaitChain.restype=W.BOOL
        session=a.OpenThreadWaitChainSession(0,None)
        if not session:
            emit(dict(stage='wait_chain',status='session_unavailable',winerror=C.get_last_error()));return
        try:
            emit(dict(stage='wait_chain_start',thread_count=len(ids),selected=ids[:4],omitted=max(0,len(ids)-4)))
            for tid in ids[:4]:
                if not process.is_running() or abs(process.create_time()-created)>.001:
                    emit(dict(stage='wait_chain',status='identity_lost'));return
                nodes=(Node*16)();count=W.DWORD(16);cycle=W.BOOL()
                ok=a.GetThreadWaitChain(session,0,0,tid,C.byref(count),nodes,C.byref(cycle))
                record=dict(stage='wait_chain',thread=tid,status='read' if ok else 'unavailable')
                if not ok:record['winerror']=C.get_last_error()
                else:
                    record.update(cycle=bool(cycle.value),nodes=[],omitted=max(0,count.value-8))
                    for node in nodes[:min(count.value,8)]:
                        item=dict(kind=node.kind,status=node.status)
                        if node.kind==8:
                            v=node.details.thread;item.update(process_id=v.pid,thread=v.tid,wait_time=v.wait_time,context_switches=v.switches)
                        record['nodes'].append(item)
                if not process.is_running() or abs(process.create_time()-created)>.001:
                    record=dict(stage='wait_chain',thread=tid,status='identity_lost')
                emit(record)
        finally:a.CloseThreadWaitChainSession(session)
    finally:k.CloseHandle(handle)


if __name__=='__main__':
    try:capture(int(sys.argv[1]),float(sys.argv[2]),int(sys.argv[3]))
    except Exception as error:
        emit(dict(stage='capture',status='unavailable',error_type=type(error).__name__,winerror=getattr(error,'winerror',None)))
