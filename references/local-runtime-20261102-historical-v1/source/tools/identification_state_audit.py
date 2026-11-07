"""List owned equipment that would be sent to the client as unidentified.

Why this exists
---------------
Native per-line identification changed the default of wire field ``0x34d``: an
equipment item with no explicit ``identified`` flag and no option line now
serializes as ``2`` (unidentified) instead of staying blank. On an existing save
that can turn gear the player already owns into "unidentified" gear, so this
tool answers one question without touching anything: which items are affected?

Audit mode never writes to the save. It copies the database to a temporary file
and reads the copy, so a run cannot leave a WAL entry or a created table behind.

``--pin`` is the escape hatch for the case where the client refuses to wear or
identify such an item: it writes the explicit ``identified=1`` flag for the
uids you name, after writing a timestamped backup next to the save.
"""
import argparse
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]


def owned_items(db):
    """Every loaded item grouped by owner, in bag order."""
    from els_server.storage.inventory_state import load_items
    for (owner,) in db.execute('SELECT DISTINCT owner FROM inventory_items ORDER BY owner'):
        yield owner, load_items(db, owner)


def pending(items):
    from els_server.domain.identification_ui import initial_pending
    return [item for item in items if 'identified' not in item and initial_pending(item)]


def describe(item):
    from els_server.domain import identification_ui as ui
    from els_server.game_data import client_data
    profile = ui.native_profile(item['template']) or ui.compatibility_profile(item['template']) or {}
    try:
        name = client_data().item(item['template']).get('name') or '?'
    except Exception:
        name = '?'
    return len(profile.get('native_groups', [])), name


def flagged(db, uid):
    row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_identification'").fetchone()
    if not row:
        return False
    return db.execute('SELECT 1 FROM equipment_identification WHERE item_uid=?', (uid,)).fetchone() is not None


def audit(state):
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / 'audit.sqlite3'
        shutil.copy2(state, copy)
        db = sqlite3.connect(str(copy))
        try:
            total = 0
            rows = []
            for owner, items in owned_items(db):
                for item in pending(items):
                    lines, name = describe(item)
                    rows.append((owner, item['uid'], item['template'], item['group'], item['slot'], lines, name))
                total += len(items)
            print('存档 %s' % state)
            print('物品总数 %d，其中会按「未鉴定」下发的 %d 件' % (total, len(rows)))
            if rows:
                print()
                print('%-6s %-9s %-7s %-4s %-4s %-6s %s' % ('角色', 'uid', '模板', '背包', '槽', '原生行数', '名字'))
                for row in rows:
                    print('%-6d %-9d %-7d %-4d %-4d %-6d %s' % row)
                print()
                print('注：这里只读副本，存档未改动。')
                print('   若客户端不让穿/不让鉴定，用 --pin 指定 uid 把它标成已鉴定。')
            return 0
        finally:
            db.close()


def pin(state, uids):
    backup = state.with_name(state.stem + '-backup-' + time.strftime('%Y%m%d-%H%M%S') + state.suffix)
    shutil.copy2(state, backup)
    print('备份：%s' % backup)
    db = sqlite3.connect(str(state))
    db.isolation_level = None
    try:
        from els_server.storage.equipment_identification import ensure
        ensure(db)
        known = {row[0] for row in db.execute('SELECT uid FROM inventory_items')}
        missing = [uid for uid in uids if uid not in known]
        if missing:
            raise SystemExit('存档里没有这些 uid：%s' % missing)
        db.execute('BEGIN')
        for uid in uids:
            db.execute('INSERT INTO equipment_identification VALUES (?,1) '
                       'ON CONFLICT(item_uid) DO UPDATE SET identified=1', (uid,))
        db.execute('COMMIT')
        print('已把 %d 件标成已鉴定：%s' % (len(uids), ' '.join(str(uid) for uid in uids)))
        return 0
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--state', default=str(ROOT / 'state/development.sqlite3'))
    parser.add_argument('--pin', nargs='+', type=int, metavar='UID')
    options = parser.parse_args()
    state = Path(options.state)
    if not state.exists():
        raise SystemExit('找不到存档：%s' % state)
    if options.pin:
        return pin(state, options.pin)
    return audit(state)


if __name__ == '__main__':
    raise SystemExit(main())
