"""Internal profile persistence, shared by native mount list/summon snapshots.

No network mutation is enabled here. Race/reset callers must perform their own
authoritative result, inventory transaction and operation receipt before save.
"""
from els_server.domain.mount_racing_rules import profile
from els_server.storage.character_schema import character_uid


def read(db, owner, uid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mount_growth'").fetchone():
        return profile()
    row = db.execute('SELECT owner,experience,start,acceleration,breakthrough,spurt FROM mount_growth WHERE uid=?', (uid,)).fetchone()
    if row is None:
        return profile()
    if row[0] != owner:
        raise ValueError('Mount growth owner mismatch')
    return profile(row[1], dict(enumerate(row[2:])))


def save(db, owner, uid, value):
    """Store a complete computed profile inside the caller's transaction."""
    if not db.in_transaction:
        raise ValueError('Mount growth requires explicit transaction')
    owner = character_uid(owner)
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.mount_state import owned
    require_active_character(db, owner)
    mount = owned(db, owner, uid)
    if 'expires_at' in mount or mount['unit'] >= 10000:
        raise ValueError('Permanent player mount required')
    checked = profile(value['experience'], value['stats'])
    if value['level'] != checked['level']:
        raise ValueError('Mount growth level mismatch')
    db.execute('''CREATE TABLE IF NOT EXISTS mount_growth (
        uid INTEGER PRIMARY KEY REFERENCES companions(uid),owner INTEGER NOT NULL,
        experience INTEGER NOT NULL CHECK(experience BETWEEN 0 AND 11300),
        start INTEGER NOT NULL CHECK(start BETWEEN 0 AND 10),
        acceleration INTEGER NOT NULL CHECK(acceleration BETWEEN 0 AND 10),
        breakthrough INTEGER NOT NULL CHECK(breakthrough BETWEEN 0 AND 10),
        spurt INTEGER NOT NULL CHECK(spurt BETWEEN 0 AND 10))''')
    old = db.execute('SELECT owner FROM mount_growth WHERE uid=?', (uid,)).fetchone()
    if old and old[0] != owner:
        raise ValueError('Mount growth owner mismatch')
    db.execute('''INSERT INTO mount_growth VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET experience=excluded.experience,start=excluded.start,
        acceleration=excluded.acceleration,breakthrough=excluded.breakthrough,spurt=excluded.spurt''',
        (uid, owner, checked['experience'], *(checked['stats'].get(i, 0) for i in range(4))))
    return checked
