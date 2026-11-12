"""Counts come from committed business receipts, including their retained history."""

TABLES=('native_player_trades','player_mail_receipts','fishing_attempts','pet_expedition_receipts','native_guild_actions')


def present(db):
    return {r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name IN("
        +','.join('?'for _ in TABLES)+')',TABLES)}


def ensure_indexes(db):
    # Called from achievement persistence, not its read-only source projector.
    tables=present(db)
    if 'native_player_trades'in tables:
        db.execute("CREATE INDEX IF NOT EXISTS native_achievement_trade_account_a ON native_player_trades(json_extract(ledger_json,'$[0].account'))")
        db.execute("CREATE INDEX IF NOT EXISTS native_achievement_trade_account_b ON native_player_trades(json_extract(ledger_json,'$[1].account'))")
    if 'player_mail_receipts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_post_sender ON player_mail_receipts(account_id)')
    if 'fishing_attempts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_fishing_account ON fishing_attempts(account,caught,fish)')
    if 'pet_expedition_receipts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_expedition_account ON pet_expedition_receipts(account,action)')
    if 'native_guild_actions'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_guild_owner_kind ON native_guild_actions(owner,kind)')


def counts(db,account,condition_types):
    if not condition_types&{24,27,28,61,62,63}:return {}
    tables=present(db);result={}
    if 24 in condition_types and 'native_guild_actions'in tables:
        result[(24,0)]=db.execute('SELECT COUNT(*)FROM native_guild_actions a JOIN character_owners o ON o.uid=a.owner '
            'WHERE o.account_id=?AND a.kind=?',(account,0x6c8)).fetchone()[0]
    if 27 in condition_types and 'native_player_trades'in tables:
        # perform() seals exactly two different accounts. One trade counts
        # once for each participant, independent of its two inventory receipts.
        result[(27,0)]=db.execute("SELECT COUNT(*)FROM native_player_trades WHERE "
            "json_extract(ledger_json,'$[0].account')=?OR json_extract(ledger_json,'$[1].account')=?",(account,account)).fetchone()[0]
    if 28 in condition_types and 'player_mail_receipts'in tables:
        result[(28,0)]=db.execute('SELECT COUNT(*)FROM player_mail_receipts WHERE account_id=?',(account,)).fetchone()[0]
    if condition_types&{61,62}and 'fishing_attempts'in tables:
        # Each settled attempt, including a miss, is one61. Only the actual
        # committed caught item contributes to62, never a bait debit or retry.
        groups=list(db.execute('SELECT caught,fish,COUNT(*)FROM fishing_attempts WHERE account=?GROUP BY caught,fish',(account,)))
        if 61 in condition_types:result[(61,0)]=sum(n for _,_,n in groups)
        if 62 in condition_types:
            result.update({(62,fish):n for caught,fish,n in groups if caught and fish is not None})
    if 63 in condition_types and 'pet_expedition_receipts'in tables:
        result[(63,0)]=db.execute("SELECT COUNT(*)FROM pet_expedition_receipts WHERE account=?AND action='complete'",(account,)).fetchone()[0]
    return result
