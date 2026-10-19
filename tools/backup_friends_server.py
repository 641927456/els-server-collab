"""Consistent online SQLite backups; use the backup API rather than copying WAL files."""
import argparse
from contextlib import closing
import datetime
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.config import ServerConfig


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args(argv);config=ServerConfig.load(args.config)
    folder=args.destination.resolve()/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');folder.mkdir(parents=True)
    for name,source in (('game.sqlite3',config.state_file),('accounts.sqlite3',config.accounts_file)):
        if source is None or not source.is_file():raise ValueError('Missing backup source: '+name)
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(folder/name)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Backup failed integrity check')
    print(folder)


if __name__=='__main__':main()
