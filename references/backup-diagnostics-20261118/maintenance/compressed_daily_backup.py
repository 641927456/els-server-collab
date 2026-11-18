"""Run the existing SQLite backup command, then losslessly compress its output."""
import argparse
import ctypes
import datetime
import gzip
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
import uuid

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                              ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
kernel.CreateFileW.restype = ctypes.c_void_p
kernel.SetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
kernel.SetFileInformationByHandle.restype = ctypes.c_int
kernel.CloseHandle.argtypes = [ctypes.c_void_p]
kernel.GetCurrentProcess.restype = ctypes.c_void_p
kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
kernel.SetPriorityClass.restype = ctypes.c_int


def digest_stream(stream):
    digest = hashlib.sha256()
    count = 0
    for block in iter(lambda: stream.read(4*1024**2), b''):
        digest.update(block)
        count += len(block)
    return count, digest.hexdigest()


def verify_archive(path, expected_bytes, expected_sha256):
    with gzip.open(path, 'rb') as stream:
        count, digest = digest_stream(stream)
    if (count, digest) != (expected_bytes, expected_sha256):
        raise ValueError('Compressed backup does not reproduce the original bytes')


def compress_database(path, destination):
    path, destination = Path(path).resolve(), Path(destination).resolve()
    if path.parent.parent != destination or not re.fullmatch(r'\d{8}-\d{6}-\d+', path.parent.name):
        raise ValueError('Not a dated backup beneath the specified destination')
    if path.name not in ('game.sqlite3', 'accounts.sqlite3'):
        raise ValueError('Not a recognized backup database')
    if any(p.lstat().st_file_attributes & 0x400 for p in (path, *path.parents)):
        raise ValueError('Backup path crosses a reparse point')
    if any(Path(str(path)+suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Backup has SQLite sidecars; leave it unchanged')
    archive = path.with_name(path.name+'.gz')
    record = path.with_name(path.name+'.archive.json')
    if archive.exists() or record.exists():
        raise FileExistsError('An archive or compression record already exists')
    partial = path.with_name(path.name+'.gz.part-'+uuid.uuid4().hex)
    handle = kernel.CreateFileW(str(path), 0x80010000, 0, None, 3, 0x08200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    try:
        with os.fdopen(fd, 'rb') as source:
            original = os.fstat(source.fileno())
            digest = hashlib.sha256()
            count = 0
            with partial.open('xb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1, mtime=0) as zipped:
                    for block in iter(lambda: source.read(4*1024**2), b''):
                        digest.update(block)
                        count += len(block)
                        zipped.write(block)
                raw.flush()
                os.fsync(raw.fileno())
            if count != original.st_size:
                raise ValueError('Source length changed while being compressed')
            verify_archive(partial, count, digest.hexdigest())
            with partial.open('rb') as saved:
                archive_bytes, archive_sha256 = digest_stream(saved)
            partial.rename(archive)
            result = dict(original=path.name, archive=archive.name, original_bytes=count,
                          original_sha256=digest.hexdigest(), compressed_bytes=archive_bytes,
                          compressed_sha256=archive_sha256, roundtrip_verified=True, compression='gzip-level1',
                          created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            with record.open('x', encoding='utf8') as stream:
                json.dump(result, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            delete = ctypes.c_ubyte(1)
            if not kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(delete), ctypes.sizeof(delete)):
                raise ctypes.WinError(ctypes.get_last_error())
        if path.exists():
            raise RuntimeError('Original backup is still present after verified compression')
        return result
    finally:
        if partial.exists():
            partial.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args(argv)
    logs = Path(__file__).resolve().parents[1]/'logs/backups'
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    with (logs/(stamp+'-'+uuid.uuid4().hex+'.log')).open('x', encoding='utf8') as diagnostic:
        try:
            if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00100000):
                raise ctypes.WinError(ctypes.get_last_error())
            original = Path(__file__).resolve().parents[1]/'tools/backup_friends_server.py'
            completed = subprocess.run([sys.executable, '-B', str(original), '--config', str(args.config),
                                        '--destination', str(args.destination)], check=True,
                                       stdout=subprocess.PIPE, stderr=diagnostic, text=True, encoding='utf8',
                                       creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            folder = Path(completed.stdout.strip()).resolve()
            if folder.parent != args.destination.resolve():
                raise ValueError('Backup command returned an unexpected directory')
            for name in ('game.sqlite3', 'accounts.sqlite3'):
                compress_database(folder/name, args.destination)
            print(folder)
        except BaseException:
            traceback.print_exc(file=diagnostic)
            diagnostic.flush()
            os.fsync(diagnostic.fileno())
            raise



if __name__ == '__main__':
    main()
