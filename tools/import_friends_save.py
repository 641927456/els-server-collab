"""Copy a local save with SQLite backup, then assign that COPY to its remote owner."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def copy_save(source,destination,account_id):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or destination.exists():raise ValueError('Destination must be a new separate save')
    if type(account_id) is not int or not 2<=account_id<2**63:raise ValueError('Expected a remote owner account')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb'):pass
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(destination)) as copied:
            original.backup(copied)
            if copied.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Copied save failed integrity check')
            with copied:
                copied.execute('CREATE TABLE IF NOT EXISTS character_owners (uid INTEGER PRIMARY KEY REFERENCES characters(uid), account_id INTEGER NOT NULL CHECK(account_id>0))')
                if copied.execute('SELECT 1 FROM character_owners WHERE account_id<>1 LIMIT 1').fetchone():raise ValueError('Source is already a multiplayer save; ownership must not be reassigned')
                copied.execute('INSERT OR IGNORE INTO character_owners SELECT uid,1 FROM characters')
                copied.execute('UPDATE character_owners SET account_id=?',(account_id,))
            return dict(characters=copied.execute('SELECT COUNT(*) FROM characters').fetchone()[0],account_id=account_id)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True);parser.add_argument('--account-id',type=int,required=True)
    args=parser.parse_args();print(json.dumps(copy_save(args.source,args.destination,args.account_id)))
