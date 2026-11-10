"""Marriage titles reuse the existing owned-title lifecycle and expiry reader."""
from els_server.storage import relationships, titles

DAY = 86400
NEWLYWED = 12360
ANNIVERSARIES = ((100, 11140), (200, 11150), (365, 11160))


def earned(db, character, now):
    saved = relationships.snapshot(db, character['uid'], character['account_id'])
    if saved is None or saved['kind'] != 2:
        return ()
    first, refreshed = saved['created_at'], saved['refreshed_at']
    if not 0 < first <= refreshed <= now:
        raise ValueError('Marriage title source clock')
    result = [(NEWLYWED, refreshed, refreshed + 30 * DAY)]
    result.extend((title, first + days * DAY, 0)
                  for days, title in ANNIVERSARIES if first + days * DAY <= now)
    return tuple(result)


def missing(db, character, rewards):
    for title, start, end in rewards:
        old = db.execute("SELECT acquired_at,expires_at FROM title_ownership "
                         "WHERE scope='character' AND subject=? AND title=?",
                         (character['uid'], title)).fetchone()
        if old is None or end and old[1] and old[1] < end:
            return True
    return False


def grant(db, character, rewards):
    if not db.in_transaction:
        raise ValueError('Marriage titles require the original writer')
    titles.schema(db)
    for title, start, end in rewards:
        # Keep permanent/longer existing ownership and the player's selection.
        db.execute('''INSERT INTO title_ownership VALUES ('character',?,?,?,?,?)
            ON CONFLICT(scope,subject,title) DO UPDATE SET
                acquired_by=excluded.acquired_by,acquired_at=excluded.acquired_at,
                expires_at=excluded.expires_at
            WHERE excluded.expires_at>0 AND title_ownership.expires_at>0
                AND excluded.expires_at>title_ownership.expires_at''',
            (character['uid'], title, character['name'], start, end))


def synchronize(db, owner, now):
    character = titles.character(db, owner)
    grant(db, character, earned(db, character, now))
