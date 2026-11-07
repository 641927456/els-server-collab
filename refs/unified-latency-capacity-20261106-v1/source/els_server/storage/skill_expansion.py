"""Character-owned permanent skill expansion, inside the caller's transaction."""
def ensure_expansions(db):
    db.execute('CREATE TABLE IF NOT EXISTS character_skill_expansions (uid INTEGER PRIMARY KEY REFERENCES characters(uid), ordinary INTEGER NOT NULL CHECK(ordinary=1))')


def is_expanded(db,uid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_skill_expansions'").fetchone():return False
    return db.execute('SELECT 1 FROM character_skill_expansions WHERE uid=?',(uid,)).fetchone() is not None


def grant_ordinary(db,uid):
    ensure_expansions(db)
    if not db.execute('SELECT 1 FROM characters WHERE uid=?',(uid,)).fetchone():raise ValueError('Unknown expansion owner')
    if is_expanded(db,uid):raise ValueError('Skill row already expanded')
    db.execute('INSERT INTO character_skill_expansions VALUES (?,1)',(uid,))
