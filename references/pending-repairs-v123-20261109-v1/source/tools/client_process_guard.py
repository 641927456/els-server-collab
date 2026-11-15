"""Check named game processes without treating exited Windows objects as live."""

import ctypes
from ctypes import wintypes

import psutil


_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


def _is_running(pid):
    handle = _kernel32.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: process disappeared
            return False
        if error == 5:  # ERROR_ACCESS_DENIED: termination is unconfirmed
            return True
        raise ctypes.WinError(error)
    try:
        status = _kernel32.WaitForSingleObject(handle, 0)
        if status == 0:  # WAIT_OBJECT_0: the process has terminated
            return False
        if status == 258:  # WAIT_TIMEOUT: still running
            return True
        if status == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        raise OSError('Unexpected process wait status: ' + str(status))
    finally:
        if not _kernel32.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def has_running_client():
    return any(
        _is_running(process.pid)
        for process in psutil.process_iter(['name'])
        if (process.info['name'] or '').lower() in ('x2.exe', 'x2_dx11.exe')
    )
