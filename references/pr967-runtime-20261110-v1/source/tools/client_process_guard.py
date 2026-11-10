"""Tell a genuinely running native client apart from a lingering process object.

A crashed or force-killed ``x2_dx11.exe`` can leave its *process object* behind.
The kernel keeps that object alive for as long as anything still holds a handle
to it, so psutil keeps listing it -- with ``status='stopped'``, ``num_threads()==0``
and ``num_handles()==0`` -- and even ``GetExitCodeProcess`` keeps answering 259.
259 is ``STILL_ACTIVE``, but it is also the very value the image hands to
``ExitProcess`` when it dies on its own, so the two cases are indistinguishable
from the exit code and a name-only check reports a phantom "game already
running" that no ``taskkill`` can ever clear.

``WaitForSingleObject(h, 0)`` is the authoritative test instead: a terminated
process object is signalled (``WAIT_OBJECT_0``), a live one times out
(``WAIT_TIMEOUT``). Verified against PID 4772 on this machine, which sat at
0 threads / 0 handles / "exit code 259" while already being signalled.
"""
import ctypes
from ctypes import wintypes

CLIENT_NAMES = ('x2.exe', 'x2_dx11.exe')

_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WAIT_TIMEOUT = 258

_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def terminated(pid):
    """True when *pid* has finished, even if its process object still lingers.

    A process we cannot open (already gone, or owned by a higher integrity
    level) is reported as terminated on purpose: blocking every launch behind a
    process we may not even inspect is worse than attempting the start.
    """
    handle = _kernel32.OpenProcess(
        _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return True
    try:
        return _kernel32.WaitForSingleObject(handle, 0) != _WAIT_TIMEOUT
    finally:
        _kernel32.CloseHandle(handle)


def running_clients():
    """Return ``[(pid, name)]`` for clients that are genuinely still running."""
    import psutil
    live = []
    for proc in psutil.process_iter(['name', 'pid']):
        name = proc.info['name'] or ''
        if name.lower() not in CLIENT_NAMES:
            continue
        if terminated(proc.info['pid']):
            continue
        live.append((proc.info['pid'], name))
    return live
