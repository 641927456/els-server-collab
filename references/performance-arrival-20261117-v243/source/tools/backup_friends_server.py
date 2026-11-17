"""Consistent online SQLite backups; use the backup API rather than copying WAL files."""
import argparse
from contextlib import closing
import ctypes
import datetime
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.config import ServerConfig


def backup_database(source,target):
    # The daily wrapper retains this file until its gzip copy has been verified.
    # Compress the new destination before SQLite opens it, as publication backups do.
    reserve=1024**3+32*1024**2
    def headroom(*_):
        if shutil.disk_usage(target.parent).free<reserve:
            raise OSError('Backup physical free-space reserve reached')
    headroom()
    target.touch(exist_ok=False)
    subprocess.run(['compact.exe','/C','/I','/Q',str(target)],check=True,capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    attributes=ctypes.windll.kernel32.GetFileAttributesW(str(target))
    if attributes==0xffffffff or not attributes&0x800:
        raise OSError('Backup destination is not NTFS compressed')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:
        # Keep one source snapshot while stepping, even as online WAL writers commit.
        src.execute('BEGIN');src.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone()
        src.backup(dst,pages=4096,progress=headroom,sleep=.01)
        if dst.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Backup failed integrity check')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args(argv);config=ServerConfig.load(args.config)
    folder=args.destination.resolve()/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');folder.mkdir(parents=True)
    for name,source in (('game.sqlite3',config.state_file),('accounts.sqlite3',config.accounts_file)):
        if source is None or not source.is_file():raise ValueError('Missing backup source: '+name)
        backup_database(source,folder/name)
    print(folder)


if __name__=='__main__':main()
