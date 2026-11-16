"""One character's weekly Temple reward balance."""
from els_server.storage.raid_economy_state import week_at

MAXIMUM = 10


def used(db, owner, now):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='atma_temple_fragment_weeks'").fetchone():
        return 0
    row=db.execute("SELECT count FROM atma_temple_fragment_weeks WHERE owner=? AND week=?",
                   (owner,week_at(now))).fetchone()
    return row[0] if row else 0


def spend(db, owner, now):
    db.execute("""CREATE TABLE IF NOT EXISTS atma_temple_fragment_weeks (
        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
        week TEXT NOT NULL, count INTEGER NOT NULL CHECK(count BETWEEN 1 AND 10),
        PRIMARY KEY(owner,week))""")
    return db.execute("""INSERT INTO atma_temple_fragment_weeks VALUES (?,?,1)
        ON CONFLICT(owner,week) DO UPDATE SET count=count+1 WHERE count<?""",
        (owner,week_at(now),MAXIMUM)).rowcount==1


def restore(db, owner, now):
    count=used(db,owner,now)
    if not count:
        raise ValueError("Temple reward balance already full")
    key=(owner,week_at(now))
    if count==1:
        db.execute("DELETE FROM atma_temple_fragment_weeks WHERE owner=? AND week=?",key)
    else:
        db.execute("UPDATE atma_temple_fragment_weeks SET count=count-1 WHERE owner=? AND week=?",key)
