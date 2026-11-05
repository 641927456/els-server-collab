"""Conservative, connection-local checks for the existing constructor writers.

Only an exact known schema and an already-complete seed/migration state may
skip a writer. Unknown schemas keep the old writer and its errors. There is
no readiness cache: every construction checks its own connection snapshot.
"""
import re
from els_server.storage.character_schema import TABLE_KEYS


LOCAL = {
    'location': 'CREATE TABLE location (uid INTEGER PRIMARY KEY CHECK(uid>=1001), town INTEGER NOT NULL, board INTEGER NOT NULL CHECK(board>=0 AND board<255), progress INTEGER NOT NULL CHECK(progress>=0 AND progress<=100), x REAL NOT NULL, y REAL NOT NULL, z REAL NOT NULL, revision INTEGER NOT NULL)',
    'ui_layout': 'CREATE TABLE ui_layout (uid INTEGER PRIMARY KEY CHECK(uid>=1001), payload BLOB NOT NULL, revision INTEGER NOT NULL)',
    'key_bindings': 'CREATE TABLE key_bindings (uid INTEGER PRIMARY KEY CHECK(uid>=1001), payload BLOB NOT NULL, revision INTEGER NOT NULL)',
    'skill_slots': 'CREATE TABLE skill_slots (uid INTEGER PRIMARY KEY CHECK(uid>=1001), payload BLOB NOT NULL, revision INTEGER NOT NULL)',
}
REWARD = {
    'reward_balances': 'CREATE TABLE reward_balances (uid INTEGER PRIMARY KEY CHECK(uid>=1001), ed INTEGER NOT NULL CHECK(ed>=0), experience INTEGER NOT NULL CHECK(experience>=0), revision INTEGER NOT NULL CHECK(revision>=0))',
    'reward_receipts': 'CREATE TABLE reward_receipts (run_id TEXT PRIMARY KEY, proof_sha256 TEXT NOT NULL, grant_json TEXT NOT NULL, response BLOB NOT NULL, balance_json TEXT NOT NULL)',
    'reward_title_receipts': 'CREATE TABLE reward_title_receipts (run_id TEXT PRIMARY KEY REFERENCES reward_receipts(run_id), owner INTEGER NOT NULL, effect_json TEXT NOT NULL)',
    'dungeon_records': 'CREATE TABLE dungeon_records (uid INTEGER NOT NULL, map_id INTEGER NOT NULL, seconds INTEGER NOT NULL CHECK(seconds>0 AND seconds<=2147483647), PRIMARY KEY(uid,map_id))',
}
INVENTORY = {
    'inventory_items': 'CREATE TABLE inventory_items (uid INTEGER PRIMARY KEY CHECK(uid>0), owner INTEGER NOT NULL CHECK(owner>=1001), template INTEGER NOT NULL, metadata INTEGER NOT NULL, count INTEGER NOT NULL CHECK(count>0), bag_group INTEGER NOT NULL, slot INTEGER NOT NULL, UNIQUE(owner,bag_group,slot))',
    'inventory_sequence': 'CREATE TABLE inventory_sequence (id INTEGER PRIMARY KEY CHECK(id=1), next_uid INTEGER NOT NULL CHECK(next_uid>0))',
    'reward_inventory_receipts': 'CREATE TABLE reward_inventory_receipts (run_id TEXT PRIMARY KEY REFERENCES reward_receipts(run_id), items_json TEXT NOT NULL)',
    'inventory_migrations': 'CREATE TABLE inventory_migrations (name TEXT PRIMARY KEY, audit_json TEXT NOT NULL)',
    'equipment_attributes': 'CREATE TABLE equipment_attributes (item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED, slot0 INTEGER NOT NULL CHECK(slot0 BETWEEN 0 AND 6), slot1 INTEGER NOT NULL CHECK(slot1 BETWEEN 0 AND 6), slot2 INTEGER NOT NULL CHECK(slot2 BETWEEN 0 AND 6), slot3 INTEGER NOT NULL CHECK(slot3 BETWEEN 0 AND 6))',
}


def _definition(sql):
    # These pinned definitions contain no string literals or quoted column
    # names. Permit only whitespace, keyword case and SQLite's table quoting.
    sql = re.sub(r'^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?(\w+)"?',
                 lambda match: 'CREATE TABLE ' + match[1], sql.strip(), flags=re.I)
    return re.sub(r'\s+', '', sql).lower()


def schema_ready(db, expected):
    names = tuple(dict.fromkeys((*TABLE_KEYS, *expected)))
    marks = ','.join('?' for _ in names)
    definitions = dict(db.execute('SELECT name,sql FROM sqlite_master WHERE type=\'table\' AND name IN (' + marks + ')', names))
    for table, key in TABLE_KEYS.items():
        if f'CHECK({key}=1001)' in definitions.get(table, ''):
            return False
    if any(table not in definitions or _definition(definitions[table]) != _definition(sql)
           for table, sql in expected.items()):
        return False
    # INSERT OR IGNORE can still fire a BEFORE INSERT trigger on an existing
    # seed. Preserve that original behavior by falling back for custom triggers.
    names = tuple(expected)
    return not db.execute('SELECT 1 FROM sqlite_master WHERE type=\'trigger\' AND tbl_name IN (' + ','.join('?' for _ in names) + ') LIMIT 1', names).fetchone()


def read_ready(db, check, *args):
    if db.in_transaction:
        raise ValueError('Initialization probe requires its own read snapshot')
    db.execute('BEGIN')
    try:
        return check(db, *args)
    finally:
        db.rollback()


def local_ready(db, uid):
    if db.execute('PRAGMA user_version').fetchone() != (1,) or not schema_ready(db, LOCAL):
        return False
    row = db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?', (uid,)).fetchone()
    if row is None:
        return False
    from els_server.storage.local_state import validate_location
    try:
        validate_location(row[0], row[1], row[2], row[3:6])
    except (ValueError, TypeError):
        return False
    return True


def reward_ready(db, uid):
    if not schema_ready(db, REWARD):
        return False
    row = db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (uid,)).fetchone()
    from els_server.storage.reward_state import validate_balances
    try:
        validate_balances(row)
    except ValueError:
        return False
    return True


def inventory_ready(db,owner=1001):
    if not schema_ready(db, INVENTORY):
        return False
    row = db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()
    if row is None or type(row[0]) is not int or row[0] <= 0:
        return False
    # The potion migration always validates owner 1001 and persists its audit,
    # even when it moves no item. Never replace that work with a done marker.
    if not db.execute('SELECT 1 FROM inventory_migrations WHERE name=?', ('potion-77000-accessory-to-quick-slot-v1',)).fetchone():
        return False
    from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
    if any(TEMPLATE_BAG_GROUPS.get(template)==7 for template, in db.execute(
            'SELECT template FROM inventory_items WHERE owner=? AND bag_group=27',(owner,))):
        return False
    if db.execute('SELECT 1 FROM inventory_migrations WHERE name=?', ('ice-heater-fashion-native-bag-27-v1',)).fetchone():
        return True
    # Fashion intentionally leaves no marker when there were no changes. A
    # later legacy row must still be discovered; no process-wide result cache.
    from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
    return not any(TEMPLATE_BAG_GROUPS.get(template) == 27 for template, in db.execute(
        'SELECT template FROM inventory_items WHERE owner=1001 AND bag_group=7'))
