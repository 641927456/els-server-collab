"""Freeze Greed's native raw-power band in the original reward transaction."""
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import math


TABLE = 'greed_power_facts'


@lru_cache(maxsize=1)
def rates():
    from els_server.game_data import client_data
    definition = client_data().skill(900407)
    names = ('SA_FIGHTING_POWER_ABS', 'SA_STAT_DROP_REL', 'SA_MAX_DROP_RATE_REL')
    rows = {row['m_wstrName']: row['m_Value'] for key, row in definition.items()
            if key.startswith('NUMERICAL_DATA') and row['m_wstrName'] in names}
    return {rank: (float(rows[names[0]][str(rank)]),
                   int(Decimal(str(rows[names[1]][str(rank)])) * 100),
                   int(Decimal(str(rows[names[2]][str(rank)])) * 100)) for rank in (int(r) for r,v in rows[names[0]].items() if v is not None)}


def bonus(db, owner, dungeon, operation, context, rank, base):
    from els_server.domain.client_reward_power import enabled, reward_power
    if not enabled():
        return base
    if not db.in_transaction:
        raise ValueError('Greed power needs the original reward transaction')
    digest = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone()
    old = db.execute('SELECT owner,dungeon,run_id,context_sha256,basis_points FROM greed_power_facts WHERE operation=?',
                     (operation,)).fetchone() if exists else None
    if old is not None:
        if old[:4] != (owner, dungeon, context['run_id'], digest):
            raise ValueError('Greed power receipt identity changed')
        return old[4]
    if not rank:
        return 0
    reported = reward_power(db, owner, context)
    if reported is None:
        return base  # Existing clients retain the verified fixed Greed bonus.
    raw, side, source = reported
    span, step, cap = rates()[rank]
    amount = base + min(math.floor(raw / span) * step, cap)
    db.execute('''CREATE TABLE IF NOT EXISTS greed_power_facts (
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),
        dungeon INTEGER NOT NULL,run_id TEXT NOT NULL,context_sha256 TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,rank INTEGER NOT NULL,active_side INTEGER NOT NULL,
        raw_power REAL NOT NULL,basis_points INTEGER NOT NULL)''')
    db.execute('INSERT INTO greed_power_facts VALUES(?,?,?,?,?,?,?,?,?,?)',
               (operation, owner, dungeon, context['run_id'], digest, source, rank, side, raw, amount))
    return amount
